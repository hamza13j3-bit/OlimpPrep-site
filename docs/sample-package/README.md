# Problem package format

A package is a ZIP file (max **20 MB**, each test file max **5 MB**, UTF-8 everywhere):

```
problem.json                 metadata, subtasks, examples, titles
statements/kk.md             one statement per language declared in problem.json (kk | ru | en)
tests/01.in  tests/01.out    tests: NN = 2-4 digits, every listed test needs both files
hints/1.kk.md                optional hints: <level 1-3>.<lang>.md
```

`problem.json` fields: `format_version` (1), `rating`, `time_limit_ms`, `memory_limit_mb`, `source`, `year`,
`author`, `hide_tags_until_solved`, `tags` (must already exist), `translations` (`{lang: {title}}`),
`subtasks` (`[{points, tests: ["01", ...]}]`, a subtask scores only if all its tests pass) and `examples`
(test ids shown to users on the problem page; everything else stays hidden).

Rules enforced on import (`POST /archive/import`, admin, multipart field `file`):

* no absolute paths, `..`, backslashes, drive letters, symlinks, encrypted or duplicate entries (zip-slip);
* no unexpected files; every test listed in a subtask exists and every test file is used;
* all problems are reported at once as `{"errors": [{"file": ..., "message": ...}]}` (HTTP 422); nothing is
  created unless the whole package is valid.

Export an existing problem with `GET /archive/problems/{id}/export`. Build a package from a folder with
`python make_zip.py <folder> <out.zip>` (see `sample-package.zip` in this folder, built from it).
