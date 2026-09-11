"""Marks `tests` as a package.

Not decoration. Under pytest's default `prepend` import mode the directory
inserted into `sys.path` is the first parent of a test module that is NOT a
package, so without this file that directory is `tests/` itself — and neither
`classroom_core` nor `tests.conftest` is importable. With it, the walk goes up
to `backend/`, which is what both imports need.

`python -m pytest` happens to paper over this by putting the working directory
on `sys.path` first; `poetry run pytest`, which is what CI runs, does not.
"""
