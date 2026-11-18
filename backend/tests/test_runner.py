import dataclasses
import os
import shutil
import time

import pytest

from app.modules.checker.runner import CaseSpec, ProblemSpec, SubtaskSpec, check

HAS_GXX = shutil.which("g++") is not None
needs_gxx = pytest.mark.skipif(not HAS_GXX, reason="g++ not installed")

SUM_PY = "a, b = map(int, input().split())\nprint(a + b)\n"


def sum_spec(time_ms=2000, mem_mb=256):
    """Subtask 1 (40 pts): two tests. Subtask 2 (60 pts): one test with a >= 100."""
    return ProblemSpec(
        time_limit_ms=time_ms,
        memory_limit_mb=mem_mb,
        subtasks=(
            SubtaskSpec(40, (CaseSpec("1 2\n", "3\n"), CaseSpec("5 5\n", "10\n"))),
            SubtaskSpec(60, (CaseSpec("100 200\n", "300\n"),)),
        ),
    )


def test_correct_solution():
    r = check("python", SUM_PY, sum_spec())
    assert (r.tests_passed, r.tests_total, r.score, r.solved) == (3, 3, 1.0, True)


def test_result_exposes_only_four_fields():
    r = check("python", SUM_PY, sum_spec())
    assert {f.name for f in dataclasses.fields(r)} == {"tests_passed", "tests_total", "score", "solved"}


def test_wrong_answer_on_one_subtask():
    code = "a, b = map(int, input().split())\nprint(a + b + (1 if a >= 100 else 0))\n"
    r = check("python", code, sum_spec())
    assert (r.tests_passed, r.tests_total) == (2, 3)
    assert r.score == pytest.approx(0.4) and r.solved is False


def test_subtask_needs_all_tests():
    code = "a, b = map(int, input().split())\nprint(a + b if a != 5 else 0)\n"
    r = check("python", code, sum_spec())
    assert r.tests_passed == 2  # tests are counted individually
    assert r.score == pytest.approx(0.6)  # but subtask 1 earns nothing


def test_token_wise_compare():
    ok = "a, b = map(int, input().split())\nprint('  ', a + b, '\\n\\n')\n"
    assert check("python", ok, sum_spec()).solved
    bad = "a, b = map(int, input().split())\nprint(float(a + b))\n"  # 3.0 != 3
    assert check("python", bad, sum_spec()).tests_passed == 0


def test_runtime_error_and_nonzero_exit_do_not_pass():
    assert check("python", "raise ValueError\n", sum_spec()).tests_passed == 0
    code = "import sys\na, b = map(int, input().split())\nprint(a + b)\nsys.exit(1)\n"
    assert check("python", code, sum_spec()).tests_passed == 0


def test_syntax_error():
    r = check("python", "def (:\n", sum_spec())
    assert (r.tests_passed, r.tests_total, r.score, r.solved) == (0, 3, 0.0, False)


def test_infinite_loop_counts_as_failed_test_and_is_killed():
    start = time.monotonic()
    r = check("python", "while True:\n    pass\n", sum_spec(time_ms=300))
    elapsed = time.monotonic() - start
    assert (r.tests_passed, r.score, r.solved) == (0, 0.0, False)
    assert elapsed < 10  # 3 tests x (0.3 s + grace), killed each time


def test_infinite_loop_only_on_some_tests():
    code = (
        "a, b = map(int, input().split())\n"
        "while a >= 100:\n    pass\n"
        "print(a + b)\n"
    )
    r = check("python", code, sum_spec(time_ms=300))
    assert (r.tests_passed, r.tests_total) == (2, 3)
    assert r.score == pytest.approx(0.4)


def test_memory_hog_counts_as_failed_test():
    code = (
        "a, b = map(int, input().split())\n"
        "if a >= 100:\n"
        "    chunks = []\n"
        "    while True:\n"
        "        chunks.append(bytearray(50 * 1024 * 1024))\n"
        "print(a + b)\n"
    )
    r = check("python", code, sum_spec(mem_mb=128))
    assert (r.tests_passed, r.tests_total) == (2, 3)
    assert r.solved is False


def test_memory_hog_everywhere():
    r = check("python", "x = bytearray(2 * 1024**3)\nprint(1)\n", sum_spec(mem_mb=128))
    assert r.tests_passed == 0 and r.score == 0.0


def test_endless_output_is_cut_off():
    start = time.monotonic()
    r = check("python", "while True:\n    print('x' * 1000)\n", sum_spec(time_ms=5000))
    assert r.tests_passed == 0
    assert time.monotonic() - start < 15


def test_server_environment_is_not_visible(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "super-secret")
    code = "import os\nprint(os.environ.get('SECRET_KEY', 'NONE'))\n"
    spec = ProblemSpec(2000, 256, (SubtaskSpec(100, (CaseSpec("", "NONE\n"),)),))
    assert check("python", code, spec).solved


def test_runs_in_fresh_temp_dir_and_cleans_up():
    code = "import os\nprint(os.path.basename(os.getcwd()))\nopen('leak.txt', 'w').write('x')\n"
    spec = ProblemSpec(2000, 256, (SubtaskSpec(100, (CaseSpec("", "never matches"),)),))
    check("python", code, spec)
    assert not os.path.exists("leak.txt")


def test_unknown_language():
    assert check("ruby", "puts 1", sum_spec()).tests_passed == 0


def test_empty_problem_is_never_solved():
    r = check("python", SUM_PY, ProblemSpec(1000, 256, ()))
    assert (r.tests_total, r.score, r.solved) == (0, 0.0, False)


# ------------------------------ C++ ------------------------------------------

SUM_CPP = "#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b<<std::endl;}\n"


@needs_gxx
def test_cpp_correct():
    assert check("cpp", SUM_CPP, sum_spec()).solved


@needs_gxx
def test_cpp_compile_error():
    r = check("cpp", "int main( {", sum_spec())
    assert (r.tests_passed, r.tests_total, r.score, r.solved) == (0, 3, 0.0, False)


@needs_gxx
def test_cpp_infinite_loop():
    code = "int main(){ volatile int x = 0; while(true){ x = x + 1; } }\n"
    assert check("cpp", code, sum_spec(time_ms=300)).tests_passed == 0


@needs_gxx
def test_cpp_memory_hog():
    code = (
        "#include <cstring>\n#include <vector>\n"
        "int main(){ std::vector<char*> v; while(true){ char* p = new char[50<<20]; "
        "memset(p, 1, 50<<20); v.push_back(p);} }\n"
    )
    assert check("cpp", code, sum_spec(mem_mb=128)).tests_passed == 0


@needs_gxx
def test_cpp_crash():
    code = "int main(){ int* p = nullptr; return *p; }\n"
    assert check("cpp", code, sum_spec()).tests_passed == 0
