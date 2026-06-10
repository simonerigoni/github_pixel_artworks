# GitHub pixel artworks

## Data

This folder contains the data used by the project.

### Format

Each artwork is a plain text file with **exactly 7 lines** (one for each day of the week).

- Row 0 (first line): Sunday
- Row 6 (last line): Saturday

Each character in a line represents one week (column) in the contribution graph.

- Empty cells (no commit): ` ` (space), `.`, `x`, `X`, `0`
- Filled cells (commit that day):
  - `*` or `1` = level 1 (lightest green)
  - `2` = level 2
  - `3` = level 3
  - `4` / `#` / `H` / higher digits = level 4+ (darkest)

The CLI and GUI treat any value > 0 as "filled" for the purpose of creating commits. Higher numbers increase the number of commits on that day (for darker squares on the graph).

### Examples

See the files in this folder:

- `simple.txt` - a small diamond shape
- `heart.txt` - heart pattern
- `legacy.txt` - original example from the inspiration project
- `levels.txt` - demonstrates different intensity levels
- `space_invaders.txt` - fun space invader pattern

### Usage

These files can be passed to the CLI via `-i data/simple.txt --year 2025 ...`

The GUI saves and loads directly to/from this folder.

### How dates are calculated

- `--year 2025` starts the leftmost column on the first Sunday of 2025.
- `--offset-weeks N` (N = 0..52) shifts the entire pattern N weeks to the right.
- `--auto-align` uses ~1 year ago (rolling view).

Artworks are limited to at most 52 weeks (columns) wide.

See the code in `src/github_pixel_artworks/core.py` (functions like `get_first_sunday_of_year`, `apply_drawing`).

### Creating your own

Use the GUI (`uv run github-pixel-artworks-gui`) to draw interactively and save new `.txt` files here, or edit them manually in a text editor.

The files should have no trailing empty lines and consistent width across the 7 rows.