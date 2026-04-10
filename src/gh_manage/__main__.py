"""Entry point for `python -m gh_manage`. Delegates to the click CLI.

`prog_name="gh-manage"` is passed explicitly so click's help, usage, and
error output display `gh-manage` instead of `python -m gh_manage` — the
latter would leak the implementation detail that the `gh-manage` shell
wrapper dispatches via `uv run python -m gh_manage`.
"""

from gh_manage.cli import main

if __name__ == "__main__":
    main(prog_name="gh-manage")
