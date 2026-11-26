# GitHub pixel artworks

## Data

This folder contains the example artworks. The GUI also saves and loads drawings here.

### Format

An artwork is a plain text file with **exactly 7 lines**, from Sunday (first line) to Saturday (last line). Each character is one week of the contribution graph, and artworks are at most 52 weeks wide.

| Characters | Level | Commits that day |
| --- | --- | --- |
| space, `.`, `x`, `X`, `0` | 0 | none |
| `*`, `1` | 1 | 1 x multiplier |
| `2`, `3` | 2, 3 | 2 or 3 x multiplier |
| `4`, `#`, `h`, `H` | 4 | 4 x multiplier (darkest green) |
| `5` to `9` | 5 to 9 | 5 to 9 x multiplier |

Any other character is empty. Short lines are padded with empty cells and trailing blank lines are ignored. Saving writes level 1 as `*` and higher levels as digits.

### Examples

- `simple.txt`: a small diamond
- `heart.txt`: a heart
- `legacy.txt`: the example from [jarreed0/contributionartwork](https://github.com/jarreed0/contributionartwork)
- `space_invaders.txt`: a row of space invaders, a full 52 weeks wide

### Placement

- `--year 2025` starts the first column on the first Sunday of 2025.
- `--offset-weeks N` (at most 52) shifts the artwork N weeks to the right.
- `--auto-align` starts on the first Sunday of the year currently visible on your profile.

See `src/github_pixel_artworks/dates.py` for the date logic and the README's grid diagram for an example.
