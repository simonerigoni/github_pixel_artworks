# GitHub pixel artworks

[![CI](https://github.com/simonerigoni/github_pixel_artworks/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/simonerigoni/github_pixel_artworks/actions/workflows/ci.yml?query=branch%3Amain) [![License](https://img.shields.io/github/license/simonerigoni/github_pixel_artworks)](LICENSE.md) [![Python](https://img.shields.io/badge/python-3.15-blue)](pyproject.toml) [![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv) [![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit) [![Renovate](https://img.shields.io/badge/renovate-enabled-brightgreen?logo=renovatebot)](https://renovatebot.com)

## Introduction

I want to build a script that can create pixel artworks in my GitHub contributions chart.

## Software and libraries

This project uses Python 3.15 and the most important packages are:

- **GitPython** (runtime): for git repository operations and creating backdated commits
- **tkinter** (stdlib): used by the GUI for the interactive pixel editor

## Data

Have a look at the `data` folder and its [DATA.md](data/DATA.md) file.

## Local configuration

To set up a local environment and install all dependencies, run `uv sync` from the project folder.

Then run the checks with:

```bash
uv run pre-commit run --all-files
uv run pytest
```

## Code Quality

Code quality is maintained through automated checks and linting using pre-commit.

Pre-commit is a framework for managing and maintaining multi-language pre-commit hooks. A pre-commit hook is a script that runs before a commit operation in a version control system. This allows to shift left code quality checks and remediations. You can change the hooks by updateing the file `.pre-commit-config.yaml`.

To trigger the pre-commit hooks without an actual commit you can run `pre-commit run --all-files -v`.

It is also possible to run manully the individual tools:

- `uv run ruff check --fix`
- `uv run ruff format .`
- `uv run pyright .`

## Testing

Tests are implemented using `pytest` and coverage is tracked with `pytest-cov`. The detailed coverage report is genarated by the pre-commit hook and it is available in [COVERAGE.md](COVERAGE.md) file.

It is also possible to run manully the individual tests:

- `uv run pytest`
- `uv run pytest tests/test_dummy.py::test_dummy`

## Running the code

After setting up the environment with `uv sync` (and optionally `uv run pre-commit install`):

### CLI

```bash
uv run github-pixel-artworks --help
```

Key options:
- `-i, --input` (required): path to a 7-line artwork file, e.g. `data/simple.txt`
- `--year 2020`: target calendar year (recommended - starts on first Sunday of the year)
- `--art-branch artworks-2025`: use (and auto-create/switch to) a dedicated, year-specific branch for the art commits (recommended convention: `artworks-<year>`). Recommended when using this repo itself for contributions (handles stashing of your source changes).
- `--in-place`: commit directly onto the current branch (use with caution or on a dedicated branch).
- `--dry-run`: preview the dates and commit count without making changes.
- `--username yourname`: auto-scale intensity based on your current GitHub contribution max.
- `--force`: skip the dirty-repo check.

Example (dry-run preview for 2020):

```bash
uv run github-pixel-artworks -i data/simple.txt --year 2020 --dry-run
```

Example (generate on dedicated branch for this repo):

```bash
uv run github-pixel-artworks -i data/heart.txt --year 2020 --art-branch artworks-2020 --yes
git push origin artworks-2020
```

After pushing, the pattern will appear in your GitHub contribution graph for the chosen weeks in that year.

### GUI

For an interactive drawing experience (recommended for creating new art):

```bash
uv run github-pixel-artworks-gui
```

The GUI lets you:
- Click to draw on a 7-row grid (toggle cells on/off)
- Add or remove week columns
- Choose the target year (and optional offset weeks)
- Load/save grids directly to the `data/` folder
- Preview the resulting dates and commit count
- "Generate Art" button: creates the backdated commits (with optional dedicated branch + auto-stash)
- "Push to GitHub" button: pushes the current branch

The GUI is built with Python's tkinter and is fully cross-platform (though this repo's setup scripts target Windows).

## Results

The core of the tool lives in `src/github_pixel_artworks/core.py` (especially `apply_drawing`).

When you run the CLI or GUI with a grid + year:

- The 7-row grid is interpreted as weeks (columns) × days (rows, Sunday at top).
- Dates are calculated starting from the first Sunday of the target year (plus any `--offset-weeks`).
- For each "on" pixel, one or more empty commits are created with the corresponding `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`.
- Higher intensity values (2, 3, 4+) create multiple commits on that day to produce darker green squares.

These commits are "empty" (no file changes) so they don't pollute the working tree history beyond the dates.

When pushed to GitHub:
- They contribute to your public (or private, if enabled) contribution graph.
- The visual pattern from your grid will appear in the chosen year/position.
- Using `--art-branch artworks-2025` (or the GUI equivalent, which suggests year-specific names like `artworks-<year>`) keeps your normal source commits (with real dates) on `main` while the artistic backdated commits live on a separate branch.

You can see example output by looking at the contribution graph on the project owner's GitHub profile (after pushing art branches).

The `data/` folder contains ready-to-use example patterns. The GUI is the easiest way to design new ones.

**Note**: GitHub only shows contributions from the last ~12 months by default on profiles, but year-specific views and the full history are still recorded. Backdating works for any past dates (within reason).

## List of activities

In the [TODO.md](TODO.md) file you can find the list of tasks and on going activities.

## Licensing and acknowledgements

Have a look at [LICENSE.md](LICENSE.md) and many thanks to [jarreed0](https://github.com/jarreed0/contributionartwork) for the inspiration.

## Outro

I hope this repository was interesting and thank you for taking the time to check it out. On my Medium you can find a more in depth [story](https://medium.com/@simone-rigoni01/) and on my Blogspot you can find the same [post](https://simonerigoni01.blogspot.com/) in italian. Let me know if you have any question and if you like the content that I create feel free to [buy me a coffee](https://www.buymeacoffee.com/simonerigoni).