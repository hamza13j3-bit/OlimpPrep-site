"""Sandboxed (best effort, NO Docker) execution of user code.

Public surface: `check(language, code, spec) -> CheckResult`. Internally a test either
passes or not; why it failed (timeout, memory, crash, wrong output, compile error...) is
deliberately collapsed into "not passed" and is only logged server-side at DEBUG level.

Isolation (see README "Checker isolation limits"):
  * every run happens in a fresh temp dir with a minimal environment (no server secrets);
  * wall-clock timeout, output-size cap, memory limit;
  * Windows: Job Object (per-process memory limit, process-count limit, kill-on-close);
  * POSIX: setrlimit (address space, CPU, file size, core) + its own process group.
  There is NO filesystem or network isolation.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)

IS_WIN = os.name == "nt"
PYTHON_EXE = getattr(sys, "_base_executable", None) or sys.executable  # not the venv launcher
PY_STARTUP_GRACE_S = 0.3  # interpreter start-up is not charged to the solution
COMPILE_TIMEOUT_S = 30
COMPILE_MEMORY_MB = 2048
RUN_MAX_PROCS = 4  # Windows job: solution process + a few helpers at most
MAX_OUTPUT_FLOOR = 64 * 1024
MAX_OUTPUT_CAP = 16 * 1024 * 1024

LANGUAGES = ("python", "cpp")


@dataclass(frozen=True)
class CaseSpec:
    input: str
    output: str


@dataclass(frozen=True)
class SubtaskSpec:
    points: int
    tests: tuple[CaseSpec, ...]


@dataclass(frozen=True)
class ProblemSpec:
    time_limit_ms: int
    memory_limit_mb: int
    subtasks: tuple[SubtaskSpec, ...]


@dataclass(frozen=True)
class CheckResult:
    tests_passed: int
    tests_total: int
    score: float
    solved: bool


# ----------------------------------------------------------------------------
# Windows Job Objects
# ----------------------------------------------------------------------------

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll")

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _EXTENDED(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BASIC),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _k32.CreateJobObjectW.restype = ctypes.c_void_p
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [ctypes.c_void_p]
    _ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]

    _LIMIT_ACTIVE_PROCESS = 0x8
    _LIMIT_PROCESS_MEMORY = 0x100
    _LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _CREATE_SUSPENDED = 0x4
    _CREATE_NO_WINDOW = 0x08000000

    def _win_attach(p: subprocess.Popen, memory_mb: int, max_procs: int | None) -> Callable[[], None]:
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError("CreateJobObject failed")
        info = _EXTENDED()
        flags = _LIMIT_PROCESS_MEMORY | _LIMIT_KILL_ON_JOB_CLOSE
        info.ProcessMemoryLimit = memory_mb * 1024 * 1024
        if max_procs:
            flags |= _LIMIT_ACTIVE_PROCESS
            info.BasicLimitInformation.ActiveProcessLimit = max_procs
        info.BasicLimitInformation.LimitFlags = flags
        handle = int(p._handle)  # type: ignore[attr-defined]
        ok = _k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        ok = ok and _k32.AssignProcessToJobObject(job, handle)
        if not ok:
            err = ctypes.get_last_error()
            p.kill()
            _k32.CloseHandle(job)
            raise OSError(f"cannot confine process in job object (error {err})")
        _ntdll.NtResumeProcess(handle)  # the process was created suspended

        def close() -> None:
            _k32.CloseHandle(job)  # KILL_ON_JOB_CLOSE terminates the whole tree

        return close


# ----------------------------------------------------------------------------
# POSIX rlimits
# ----------------------------------------------------------------------------


def _posix_preexec(memory_mb: int, cpu_s: int, fsize: int) -> Callable[[], None]:
    def apply() -> None:
        import resource

        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def _posix_killer(p: subprocess.Popen) -> Callable[[], None]:
    def close() -> None:
        import signal

        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(p.pid, signal.SIGKILL)

    return close


# ----------------------------------------------------------------------------
# generic limited process
# ----------------------------------------------------------------------------


def _clean_env(workdir: str, with_path: bool) -> dict[str, str]:
    env = {"TEMP": workdir, "TMP": workdir, "TMPDIR": workdir, "HOME": workdir}
    if IS_WIN:
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
    if with_path:
        env["PATH"] = os.environ.get("PATH", "")
    return env


def _run_limited(
    cmd: list[str],
    *,
    cwd: str,
    stdin_path: str | None,
    stdout_path: str,
    timeout_s: float,
    memory_mb: int,
    max_output: int,
    max_procs: int | None,
    with_path: bool = False,
) -> int | None:
    """Run `cmd` confined; returns the exit code, or None if it had to be killed."""
    stdin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    stdout = open(stdout_path, "wb")
    closer: Callable[[], None] = lambda: None  # noqa: E731
    p: subprocess.Popen | None = None
    try:
        extra: dict = {}
        if IS_WIN:
            extra["creationflags"] = _CREATE_SUSPENDED | _CREATE_NO_WINDOW
        else:
            extra["start_new_session"] = True
            extra["preexec_fn"] = _posix_preexec(memory_mb, int(timeout_s) + 2, max_output + (1 << 20))
        p = subprocess.Popen(
            cmd, cwd=cwd, stdin=stdin, stdout=stdout, stderr=subprocess.DEVNULL,
            env=_clean_env(cwd, with_path), close_fds=True, **extra,
        )
        closer = _win_attach(p, memory_mb, max_procs) if IS_WIN else _posix_killer(p)
        deadline = time.monotonic() + timeout_s
        while True:
            rc = p.poll()
            if rc is not None:
                return rc
            if time.monotonic() > deadline:
                return None
            if os.path.getsize(stdout_path) > max_output:
                return None
            time.sleep(0.005)
    finally:
        if p is not None:
            with contextlib.suppress(OSError):
                p.kill()
            closer()
            with contextlib.suppress(Exception):
                p.wait(timeout=5)
        if stdin is not subprocess.DEVNULL:
            stdin.close()  # type: ignore[union-attr]
        stdout.close()


# ----------------------------------------------------------------------------
# language drivers
# ----------------------------------------------------------------------------


def _prepare(language: str, code: str, workdir: str) -> tuple[list[str], float] | None:
    """Returns (command to run one test, extra time allowance in seconds) or None if the
    program could not be built."""
    if language == "python":
        path = os.path.join(workdir, "main.py")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(code)
        return [PYTHON_EXE, "-I", "-B", "main.py"], PY_STARTUP_GRACE_S
    if language == "cpp":
        gxx = shutil.which("g++")
        if gxx is None:
            log.error("g++ not found: C++ submissions cannot be checked")
            return None
        with open(os.path.join(workdir, "main.cpp"), "w", encoding="utf-8", newline="\n") as f:
            f.write(code)
        exe = "prog.exe" if IS_WIN else "prog"
        cmd = [gxx, "-O2", "-std=c++17", "-o", exe, "main.cpp"]
        if IS_WIN:
            cmd.insert(1, "-static")  # no MinGW DLLs needed at run time (flag goes before -o)
        rc = _run_limited(
            cmd, cwd=workdir, stdin_path=None, stdout_path=os.path.join(workdir, "compile.log"),
            timeout_s=COMPILE_TIMEOUT_S, memory_mb=COMPILE_MEMORY_MB, max_output=MAX_OUTPUT_CAP,
            max_procs=None, with_path=True,
        )
        if rc != 0 or not os.path.exists(os.path.join(workdir, exe)):
            log.debug("compile failed rc=%s", rc)
            return None
        return [os.path.join(workdir, exe)], 0.0
    log.error("unsupported language %r", language)
    return None


def _same_tokens(got: bytes, expected: str) -> bool:
    return got.decode("utf-8", errors="replace").split() == expected.split()


def _run_test(cmd: list[str], extra_s: float, case: CaseSpec, spec: ProblemSpec, workdir: str) -> bool:
    in_path = os.path.join(workdir, "in.txt")
    out_path = os.path.join(workdir, "out.txt")
    with open(in_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(case.input)
    cap = min(MAX_OUTPUT_CAP, max(MAX_OUTPUT_FLOOR, 4 * len(case.output) + 4096))
    try:
        rc = _run_limited(
            cmd, cwd=workdir, stdin_path=in_path, stdout_path=out_path,
            timeout_s=spec.time_limit_ms / 1000 + extra_s, memory_mb=spec.memory_limit_mb,
            max_output=cap, max_procs=RUN_MAX_PROCS,
        )
    except OSError:
        log.exception("could not run test")
        return False
    if rc != 0:
        log.debug("test not passed: rc=%s", rc)
        return False
    with open(out_path, "rb") as f:
        return _same_tokens(f.read(cap + 1), case.output)


def _remove_workdir(path: str) -> None:
    """Delete the temp dir. On Windows a just-killed or crashed program can keep its .exe
    locked for a moment, so retry; a failure here must never change the check result."""
    for _ in range(30):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.1)
    log.warning("could not remove %s", path)
    shutil.rmtree(path, ignore_errors=True)


def check(language: str, code: str, spec: ProblemSpec) -> CheckResult:
    total = sum(len(s.tests) for s in spec.subtasks)
    max_points = sum(s.points for s in spec.subtasks)
    workdir = tempfile.mkdtemp(prefix="chk_")
    passed = earned = 0
    try:
        prepared = _prepare(language, code, workdir)
        if prepared is not None:
            cmd, extra_s = prepared
            for sub in spec.subtasks:
                results = [_run_test(cmd, extra_s, c, spec, workdir) for c in sub.tests]
                passed += sum(results)
                if all(results):
                    earned += sub.points
    finally:
        _remove_workdir(workdir)
    score = earned / max_points if max_points else 0.0
    return CheckResult(passed, total, score, bool(max_points) and earned == max_points)
