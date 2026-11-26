# AGENTS.md

Guidance for AI coding assistants working on `github-pixel-artworks`. Direct instructions from the human in the conversation override this file.

## Project

A Python tool that draws pixel art on a GitHub contribution graph by creating empty, backdated commits (`git commit-tree` on the tip's own tree, with `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE`). It has a CLI (`github-pixel-artworks`) and a Tkinter editor (`github-pixel-artworks-gui`). Users draw into a repository they own, typically their profile README repository `<username>/<username>`, on its default branch, the only place GitHub counts commits. The tool refuses to draw into its own checkout.

## Layout

- `src/github_pixel_artworks/` (src layout; never add modules at the root)
  - `__init__.py`: version and the public API (`__all__`)
  - `config.py`: every named constant (levels, palette, year range, GitHub URLs and regexes, commit marker, exit codes, GUI and diagram layout), grouped by topic
  - `artwork.py`: the 7-row file format, intensity levels, colours, drawing paths
  - `dates.py`: Sunday alignment, the auto-align window, pixel timestamps
  - `art_repo.py`: opening or cloning the target repository, its default branch, pushing
  - `github.py`: username validation, the contribution calendar, remote URLs, email and fork checks
  - `painter.py`: `preview` and `apply_drawing`, which both front ends call
  - `cli.py`, `gui.py`: the front ends
- `data/`: example artworks (see `data/DATA.md`), also where the GUI saves
- `images/`: README figures; regenerate `grid_diagram.svg` with `uv run python scripts/render_grid_diagram.py`
- `tests/`: one test module per source module; `conftest.py` provides a throwaway `git_repo`, bare `file://` remotes, and blocks the network

## Workflow

- Use `uv` for everything: `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `uv run pyright`.
- Python 3.15 (`requires-python` and `.python-version`); ruff infers its target from `requires-python`.
- Pre-commit hooks (`uv-lock`, ruff, ruff format, pyright, pytest + `COVERAGE.md`) must pass. Never use `--no-verify`.
- CI calls `simonerigoni/github/.github/workflows/python-uv-ci.yml` (pinned to v1.3). `pytest-xvfb` gives the GUI tests a display there.

## Conventions

- Type hints and docstrings on public functions; private helpers get a docstring when the why is not obvious.
- Named constants instead of magic numbers, defined in `config.py` (never module-level constants elsewhere); modern syntax (`X | None`, `type` aliases).
- User-facing messages: `Error: ...` / `Warning: ...` on stderr in the CLI; the core reports progress through its `log` callback and raises `ValueError` (bad input) or `RuntimeError` (repository state).
- Tests: descriptive names, arrange/act/assert, git behaviour against the `git_repo` fixture, never against this repository, and never the network.

## Rules that protect users

- Art commits are dated 12:00 UTC with an explicit offset: GitHub groups contributions by UTC day.
- Never delete untracked or ignored files in the target repository.
- The art-branch flow always restores the original branch and the stash (`try/finally`), and reuses an existing art branch instead of resetting it.
- Branch names are validated with `git check-ref-format` and may not start with `-`.
- GUI worker threads never touch Tk; they use `_queue_log` / `_call_in_ui`.
- Art commits are empty: never write files, never commit the index (staged work stays staged). Earlier art commits (message prefix `pixel art `) count towards each pixel, so re-runs are idempotent.
- By default commit only on the target repository's default branch, and refuse this project's checkout (`is_tool_checkout`). The art branch is advanced and always warns that it does not count until it is the default.
- GitHub only counts commits on the default branch (or `gh-pages`), with a linked email, outside forks; keep the README and the warnings accurate about that.
