# AGENTS.md

This document provides guidance for AI coding assistants (Grok, Claude, Cursor, etc.) when working on the `github-pixel-artworks` project.

## Project Overview

A Python tool for "drawing" pixel art on GitHub contribution graphs by generating backdated commits (using `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE` + `--allow-empty`).

It includes:
- A CLI (`github-pixel-artworks`)
- An interactive Tkinter GUI (`github-pixel-artworks-gui`) for visually editing 7-row grids
- Support for selecting a target year (auto-calculates the first Sunday) and optional week offset
- Dedicated branch support (`--art-branch artworks-2025` etc.) with automatic stashing/checkout for clean separation between source code and art commits. Preferred naming is `artworks-<target-year>`.

The owner primarily uses **this repository itself** as the canvas for the artwork (in-place commits on dedicated `artworks-<year>` branches, e.g. `artworks-2025`).

## Directory Structure

- `src/github_pixel_artworks/` — The main package (src layout)
  - `__init__.py` — Package init + re-exports + version
  - `core.py` — Shared pure logic (grid I/O, date helpers, `apply_drawing`, preview, etc.)
  - `cli.py` — CLI implementation + `perform_pixel_art` wrapper
  - `gui.py` — Tkinter editor (interactive grid, year selector, load/save from data/, generate + push)
- `data/` — Sample artwork definition files (`.txt`, exactly 7 lines high, variable width; use ` ` / `.` / `x` for empty, `*` / digits for filled days)
- `tests/` — Pytest tests (currently minimal / dummy)
- `my_scripts/` — Windows PowerShell helpers (Set-Up.ps1, Config.ps1, Clean-Up.ps1)
- `temp/` — Original inspiration code (jarreed0/contributionartwork) — do not modify for production
- `images/` — Screenshots and visuals (if present)
- Root config: `pyproject.toml`, `.pre-commit-config.yaml`, `uv.lock`, `README.md`, `TODO.md`, `COVERAGE.md`, `LICENSE.md`, `AGENTS.md`

**Important**: Always use the `src/` layout. Do not put new Python modules at the root.

## Development Environment & Workflow

### Setup (Windows-focused)
- Run `.\my_scripts\Set-Up.ps1` (installs Python via winget, uv, pre-commit, then `uv sync` + `pre-commit install`).
- Use `uv` for **everything**:
  - `uv sync`
  - `uv run <command>`
  - `uv run python -m pytest ...`
  - `uv run ruff ...`

Note: `pyproject.toml` declares `requires-python = ">=3.12"`, even if the setup script mentions 3.11.

### Code Quality (Mandatory)
Pre-commit hooks **must pass** before any commit. They are defined in `.pre-commit-config.yaml`:

- `uv-lock`
- `ruff` (with `--fix`)
- `ruff-format`
- `pyright`
- Local `pytest` hook (runs `pytest` with coverage and **updates** `COVERAGE.md`)

To run checks manually:
- `pre-commit run --all-files -v`
- Individual tools:
  - `uv run ruff check --fix`
  - `uv run ruff format .`
  - `uv run pyright .`
  - `uv run pytest`

Never bypass hooks. If a hook fails, fix the issue (do not use `--no-verify`).

### Testing
- Framework: `pytest` + `pytest-cov`
- Run: `uv run pytest`
- Coverage report is automatically written to `COVERAGE.md` by the pre-commit hook.
- Add real tests under `tests/` when adding features (currently mostly placeholder).

### Running
- CLI: `uv run github-pixel-artworks --help`
- GUI: `uv run github-pixel-artworks-gui`

## Coding Conventions & Style

- **Type hints** required on all public functions and important internals.
- **Docstrings** on modules, public functions, and classes (Google or NumPy style is fine; keep them useful).
- Use section dividers for organization inside files:
  ```python
  # ---------------------------------------------------------------------------
  # Grid loading / saving
  # ---------------------------------------------------------------------------
  ```
- Line length: 100 (enforced by ruff).
- Target Python: 3.12+ (ruff target-version = "py312").
- Prefer modern syntax: `list[list[int]]`, `Path | str`, etc.
- **Variable naming**: Never use single-letter variables that look like numbers or are ambiguous (`l`, `I`, `O`, `0`, etc.). Ruff E741 is enforced. Use `item`, `line`, `idx`, etc.
- Relative imports inside the package:
  ```python
  from .core import apply_drawing, load_grid
  ```
- GitPython usage:
  - Import exceptions directly: `from git.exc import GitCommandError, InvalidGitRepositoryError`
  - Use `repo.git.<command>()` for low-level ops when needed.
- GUI (Tkinter):
  - Keep the UI responsive (use threading + queue for long-running git operations).
  - Constants at the top (e.g. `DATA_DIR`, `CELL_SIZE`).
  - The grid is **always 7 rows** (Sunday at top).
- Error handling in `apply_drawing` / wrappers should be clear and user-friendly (especially around dirty repos and branch management).

## Important Behavioral Rules for This Project

- The core function is `apply_drawing(...)` in `core.py`. Both CLI and GUI ultimately call it.
- When the user is drawing art in **this repo**, prefer the dedicated branch flow (`art_branch="artworks-2025"` or similar year-specific name) + `in_place=True`. This keeps source code history (with real dates) separate from the backdated art commits. Use the year the art targets in the branch name.
- The `data/` folder contains the canonical example grids. The GUI saves/loads from there by default. Keep the 7-line format.
- `data/` files are **not** currently packaged inside the wheel (they are user/developer data).
- The project has a strong Windows bias (PowerShell setup scripts, `.venv\Scripts\...` paths in pre-commit). Be careful with path separators in scripts/config.
- When adding features, update:
  - Relevant entry points in `pyproject.toml`
  - Docs in `README.md` and `TODO.md`
  - Tests (even if minimal)
  - The pre-commit coverage hook will auto-update `COVERAGE.md`

## Common Tasks & Gotchas

- **Adding a new CLI flag**: Add it in `cli.py` `argparse`, pass it down to `perform_pixel_art` → `apply_drawing`.
- **Changing grid format or date logic**: Edit only in `core.py`. Update docstrings and GUI preview logic.
- **GUI changes**: Test that the canvas, year selector, branch checkbox, generate, and push still work. The app must remain importable without immediately opening a window for tests.
- **Lint failures**: The most common recent ones have been:
  - `E741` (ambiguous `l`)
  - `F841` (unused variables)
  - pyright issues with `git.exc` (use direct imports) and unbound exceptions in version code.
- **Packaging**: Uses `hatchling` + `sources = ["src"]`. After structural changes, run `uv build --wheel` and inspect the resulting `.whl` contents.
- **Pre-commit pytest hook**: It hard-codes a path to `.venv/Scripts/pytest.exe`. If you change the environment setup, this may need updating.
- Never commit without the hooks passing. The `uv-lock` hook is especially important.

## When in Doubt

- Read the source in `src/github_pixel_artworks/core.py` first — most business logic lives there.
- Look at `pyproject.toml` and `.pre-commit-config.yaml` for the "source of truth" on tooling and configuration.
- Check `TODO.md` for current priorities.
- Prefer small, focused changes that keep the pre-commit suite green.
- If you need to run the GUI non-interactively for testing, instantiate `PixelArtGUI(root)` but do not call `mainloop()` in tests.

## Out of Scope / Future Ideas (from TODO.md and history)

- More comprehensive tests
- Better results / gallery documentation
- CI (mentioned as done in TODO but verify current state)
- Packaging the example `data/` files or making them discoverable

This file (AGENTS.md) takes precedence for AI agent behavior on this repository. Direct instructions from the human in the current conversation always override anything written here.

Thanks for helping keep the contribution graphs artistic and the code clean!