# AGENTS.md

Guidance for AI coding assistants working on `github-pixel-artworks`. Direct instructions from the human in the conversation override this file.

## Project

A Python tool that draws pixel art on a GitHub contribution graph by creating empty, backdated commits (`GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` with `--allow-empty`). It has a CLI (`github-pixel-artworks`) and a Tkinter editor (`github-pixel-artworks-gui`). The owner draws in this repository itself, on year-specific branches named `artworks-<year>`.

## Layout

- `src/github_pixel_artworks/` (src layout; never add modules at the root)
  - `__init__.py`: version and the public API (`__all__`)
  - `artwork.py`: the 7-row file format, intensity levels, colours, drawing paths
  - `dates.py`: Sunday alignment, the auto-align window, pixel timestamps
  - `github.py`: username validation, the contribution calendar, remote URLs
  - `painter.py`: `preview` and `apply_drawing`, which both front ends call
  - `cli.py`, `gui.py`: the front ends
- `data/`: example artworks (see `data/DATA.md`), also where the GUI saves
- `images/`: README figures; regenerate `grid_diagram.svg` with `uv run python scripts/render_grid_diagram.py`
- `tests/`: one test module per source module; `conftest.py` provides a throwaway `git_repo`

## Workflow

- Use `uv` for everything: `uv sync`, `uv run pytest`, `uv run ruff check`, `uv run ruff format`, `uv run pyright`.
- Python 3.15 (`requires-python` and `.python-version`); ruff infers its target from `requires-python`.
- Pre-commit hooks (`uv-lock`, ruff, ruff format, pyright, pytest + `COVERAGE.md`) must pass. Never use `--no-verify`.
- CI calls `simonerigoni/github/.github/workflows/python-uv-ci.yml` (pinned to v1.3). `pytest-xvfb` gives the GUI tests a display there.

## Conventions

- Type hints and docstrings on public functions; private helpers get a docstring when the why is not obvious.
- Named constants instead of magic numbers; modern syntax (`X | None`, `type` aliases).
- User-facing messages: `Error: ...` / `Warning: ...` on stderr in the CLI; the core reports progress through its `log` callback and raises `ValueError` (bad input) or `RuntimeError` (repository state).
- Tests: descriptive names, arrange/act/assert, git behaviour against the `git_repo` fixture, never against this repository.

## Rules that protect users

- Art commits are dated 12:00 UTC with an explicit offset: GitHub groups contributions by UTC day.
- Never delete untracked or ignored files in the target repository.
- The art-branch flow always restores the original branch and the stash (`try/finally`), and reuses an existing art branch instead of resetting it.
- Branch names are validated with `git check-ref-format` and may not start with `-`.
- GUI worker threads never touch Tk; they use `_queue_log` / `_call_in_ui`.
- GitHub only counts commits on the default branch (or `gh-pages`); keep the README accurate about that.
