"""Capture images/gui_editor.png, images/gui_levels.png and images/pattern_tetris.png from the real GUI.

Run under a virtual display at least as large as the default window (1540x600)
plus the screen margin, for example:

    xvfb-run -a -s "-screen 0 1920x1080x24" uv run python scripts/capture_gui_screenshots.py

The grab uses Pillow's ImageGrab. The project venv does not include Pillow, so
the save step is run with the system Python (``/usr/bin/python3``) when the
current interpreter has no PIL.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from github_pixel_artworks.config import CELL_SIZE, WINDOW_SIZE
from github_pixel_artworks.gui import PixelArtGUI

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "images"
EDITOR_SHOT = IMAGES / "gui_editor.png"
LEVELS_SHOT = IMAGES / "gui_levels.png"
PATTERN_TETRIS_SHOT = IMAGES / "pattern_tetris.png"

EXAMPLE_TARGET = "https://github.com/<username>/<username>"
"""Same placeholder as the README and the earlier screenshots."""

YEAR = 2026
SHADED_FILENAME = "heart_shaded"
# Light at the top of the heart, darkest at the tip (rows are Sunday=0).
SHADE_BY_ROW = {1: 1, 2: 2, 3: 2, 4: 3, 5: 4}
SYSTEM_PYTHON = "/usr/bin/python3"
GRAB_CODE = (
    "from PIL import ImageGrab\n"
    "import sys\n"
    "bbox = tuple(int(value) for value in sys.argv[1:5])\n"
    "ImageGrab.grab(bbox=bbox).save(sys.argv[5], optimize=True)\n"
)


def settle(root: tk.Tk) -> None:
    """Let Tk map the window and finish every pending layout pass."""
    for _ in range(5):
        root.update_idletasks()
        root.update()


def grab(root: tk.Tk, path: Path) -> None:
    """Save the Tk window to ``path`` as an optimized PNG."""
    settle(root)
    x, y = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    if (width, height) != WINDOW_SIZE:
        raise RuntimeError(
            f"The window is {width}x{height}, expected {WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}. "
            "Run under a virtual display large enough for the default window, e.g. "
            'xvfb-run -a -s "-screen 0 1920x1080x24" uv run python '
            "scripts/capture_gui_screenshots.py"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _grab_python(),
        "-c",
        GRAB_CODE,
        str(x),
        str(y),
        str(x + width),
        str(y + height),
        str(path),
    ]
    subprocess.run(command, check=True)


def _grab_python() -> str:
    """Return a Python that can import Pillow, preferring this interpreter."""
    if _has_pillow(sys.executable):
        return sys.executable
    if Path(SYSTEM_PYTHON).is_file() and _has_pillow(SYSTEM_PYTHON):
        return SYSTEM_PYTHON
    raise RuntimeError(
        "Pillow is needed to save the screenshots (ImageGrab). Install it, or "
        "run this script where /usr/bin/python3 already has PIL."
    )


def _has_pillow(executable: str) -> bool:
    result = subprocess.run(
        [executable, "-c", "from PIL import ImageGrab"],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def select_drawing(app: PixelArtGUI, name: str) -> None:
    names = list(app.drawings_list.get(0, tk.END))
    if name not in names:
        raise RuntimeError(f"{name} is not in the drawings list: {names}")
    app.drawings_list.selection_clear(0, tk.END)
    app.drawings_list.selection_set(names.index(name))
    app._load_selected()


def _click(app: PixelArtGUI, row: int, column: int) -> None:
    event = SimpleNamespace(x=column * CELL_SIZE + 1, y=row * CELL_SIZE + 1)
    app._on_canvas_click(cast(tk.Event, event))


def shade_heart(app: PixelArtGUI) -> None:
    """Paint the loaded heart with levels 1 (top) to 4 (tip)."""
    for row, level in SHADE_BY_ROW.items():
        for column in range(app.columns):
            if not app.grid[row][column]:
                continue
            app.level_var.set(level)
            _click(app, row, column)
            if app.grid[row][column] == 0:  # already at that level: click erased it
                _click(app, row, column)
    app.level_var.set(4)
    app.filename_var.set(SHADED_FILENAME)


def _new_app() -> tuple[tk.Tk, PixelArtGUI]:
    root = tk.Tk()
    app = PixelArtGUI(root)
    app.year_var.set(YEAR)
    app._on_schedule_changed()
    app.target_repo_var.set(EXAMPLE_TARGET)
    settle(root)
    return root, app


def _generate_pattern(
    app: PixelArtGUI, name: str, *, width: int, seed: int, text: str = ""
) -> None:
    app.pattern_var.set(name)
    app._toggle_pattern_text()
    app.pattern_text_var.set(text)
    app._resize_grid(width)
    app._pattern_seed = seed
    app._on_generate_pattern()


def capture_readme_shots() -> list[Path]:
    """Capture the README editor screenshots, including a Tetris pattern."""
    root, app = _new_app()
    try:
        select_drawing(app, "space_invaders.txt")
        grab(root, EDITOR_SHOT)
        select_drawing(app, "heart.txt")
        shade_heart(app)
        grab(root, LEVELS_SHOT)
    finally:
        root.destroy()

    root, app = _new_app()
    try:
        _generate_pattern(app, "tetris", width=52, seed=1)
        grab(root, PATTERN_TETRIS_SHOT)
    finally:
        root.destroy()
    return [EDITOR_SHOT, LEVELS_SHOT, PATTERN_TETRIS_SHOT]


def capture_pattern_previews(out_dir: Path) -> list[Path]:
    """Capture Tetris, text and mirror patterns as they appear in the editor."""
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = [
        (out_dir / "pattern_tetris.png", "tetris", 52, 1, ""),
        (out_dir / "pattern_text.png", "text", 10, 1, "SIMONE"),
        (out_dir / "pattern_mirror.png", "mirror", 36, 7, ""),
    ]
    saved: list[Path] = []
    for path, name, width, seed, text in shots:
        root, app = _new_app()
        try:
            _generate_pattern(app, name, width=width, seed=seed, text=text)
            grab(root, path)
            saved.append(path)
        finally:
            root.destroy()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--previews",
        type=Path,
        help="Write pattern preview PNGs (tetris, text, mirror) to this folder "
        "instead of recapturing the README screenshots.",
    )
    args = parser.parse_args()
    if not os.environ.get("DISPLAY"):
        raise SystemExit(
            "No DISPLAY is set. Capture under a virtual screen, e.g.\n"
            '  xvfb-run -a -s "-screen 0 1920x1080x24" uv run python '
            "scripts/capture_gui_screenshots.py"
        )
    os.chdir(ROOT)
    paths = capture_pattern_previews(args.previews) if args.previews else capture_readme_shots()
    for path in paths:
        print(f"{path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
