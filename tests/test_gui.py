"""The Tk editor.

pytest-xvfb starts a virtual X display where Xvfb is installed (Linux and CI).
Without a display these tests are skipped locally but fail on CI, so they cannot
silently stop running there.
"""

import os
import tkinter as tk
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from github_pixel_artworks import gui
from github_pixel_artworks.artwork import EMPTY_COLOR, LEVEL_COLORS


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[gui.PixelArtGUI]:
    try:
        root = tk.Tk()
    except tk.TclError:
        if os.environ.get("CI"):
            pytest.fail("Tk could not start on CI: the virtual display (pytest-xvfb) is missing")
        pytest.skip("no display available for Tk")
    root.withdraw()
    monkeypatch.setattr(gui, "DATA_DIR", tmp_path / "data")
    yield gui.PixelArtGUI(root)
    root.destroy()


def at(row: int, column: int) -> tk.Event:
    """A fake mouse event inside the given cell."""
    event = SimpleNamespace(x=column * gui.CELL_SIZE + 1, y=row * gui.CELL_SIZE + 1)
    return cast(tk.Event, event)


def paint(app: gui.PixelArtGUI, level: int, row: int, column: int) -> None:
    app.level_var.set(level)
    app._on_canvas_click(at(row, column))


def cell_fill(app: gui.PixelArtGUI, row: int, column: int) -> str:
    return app.canvas.itemcget(f"cell_{row}_{column}", "fill")


def load(app: gui.PixelArtGUI, name: str) -> None:
    app._populate_drawings_list()
    app.drawings_list.selection_set(list(app.drawings_list.get(0, tk.END)).index(name))
    app._load_selected()


class TestPainting:
    def test_drag_paints_the_stroke_value_instead_of_toggling(self, app: gui.PixelArtGUI) -> None:
        app._on_canvas_click(at(0, 0))
        app._on_canvas_drag(at(0, 0))
        app._on_canvas_drag(at(0, 1))

        assert app.grid[0][:3] == [1, 1, 0]

    def test_click_paints_the_selected_level(self, app: gui.PixelArtGUI) -> None:
        paint(app, 3, 1, 0)
        app._on_canvas_drag(at(1, 1))

        assert app.grid[1][:3] == [3, 3, 0]
        assert cell_fill(app, 1, 0) == LEVEL_COLORS[3]

    def test_clicking_a_cell_with_the_selected_level_erases_the_stroke(
        self, app: gui.PixelArtGUI
    ) -> None:
        paint(app, 3, 1, 0)
        app._on_canvas_drag(at(1, 1))

        paint(app, 3, 1, 0)
        app._on_canvas_drag(at(1, 1))

        assert app.grid[1][:2] == [0, 0]
        assert cell_fill(app, 1, 0) == EMPTY_COLOR

    def test_clicking_with_another_level_repaints(self, app: gui.PixelArtGUI) -> None:
        paint(app, 1, 2, 2)

        paint(app, 4, 2, 2)

        assert app.grid[2][2] == 4

    def test_columns_can_be_added_and_removed_within_limits(self, app: gui.PixelArtGUI) -> None:
        paint(app, 2, 0, 9)

        app._resize_grid(app.columns + 1)
        assert app.columns == 11
        assert app.grid[0][9:] == [2, 0]

        app._resize_grid(1)
        assert app.columns == gui.MIN_COLUMNS


class TestDrawingFiles:
    def test_levels_round_trip_through_save_and_load(self, app: gui.PixelArtGUI) -> None:
        for column, level in enumerate((1, 2, 3, 4)):
            paint(app, level, 0, column)
        saved = [row[:] for row in app.grid]
        app.filename_var.set("levels")
        app._save_drawing()
        app._clear_grid()

        load(app, "levels.txt")

        assert app.grid == saved

    def test_levels_above_four_are_kept_and_shown_darkest(self, app: gui.PixelArtGUI) -> None:
        (gui.DATA_DIR / "deep.txt").write_text("9\n" * 7, encoding="utf-8")

        load(app, "deep.txt")

        assert app.grid[0] == [9]
        assert cell_fill(app, 0, 0) == LEVEL_COLORS[4]

    def test_save_refuses_names_outside_the_data_dir(
        self, app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        errors: list[str] = []
        monkeypatch.setattr(gui.messagebox, "showerror", lambda _title, msg: errors.append(msg))
        app.filename_var.set("../escaped")

        app._save_drawing()

        assert errors
        assert not (tmp_path / "escaped.txt").exists()

    def test_save_writes_into_the_data_dir(self, app: gui.PixelArtGUI) -> None:
        app.filename_var.set("ok")

        app._save_drawing()

        assert (gui.DATA_DIR / "ok.txt").exists()


def test_art_branch_follows_the_year_until_renamed(app: gui.PixelArtGUI) -> None:
    app.year_var.set(2031)
    app._on_schedule_changed()
    assert app.art_branch_var.get() == "artworks-2031"

    app.art_branch_var.set("my-branch")
    app._on_schedule_changed()
    assert app.art_branch_var.get() == "my-branch"
