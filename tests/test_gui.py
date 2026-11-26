"""Smoke tests for the Tk editor.

pytest-xvfb (dev dependency) starts a virtual X display automatically where Xvfb is
installed (Linux CI), so these run on CI. Elsewhere without a display they are skipped,
but on CI (``CI`` env var set) a missing display is a hard failure, so they can't
silently stop running.
"""

import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from github_pixel_artworks import gui


@pytest.fixture
def app(tmp_path, monkeypatch):
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


def _event(r: int, c: int) -> SimpleNamespace:
    return SimpleNamespace(x=c * gui.CELL_SIZE + 1, y=r * gui.CELL_SIZE + 1)


def test_drag_paints_instead_of_toggling(app):
    app._on_canvas_click(_event(0, 0))
    app._on_canvas_drag(_event(0, 0))  # same cell again must not flip it back
    app._on_canvas_drag(_event(0, 1))
    assert app.grid[0][:3] == [1, 1, 0]
    app._on_canvas_click(_event(0, 0))  # starting on a filled cell erases
    app._on_canvas_drag(_event(0, 1))
    assert app.grid[0][:2] == [0, 0]


def test_save_rejects_path_traversal(app, tmp_path, monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(gui.messagebox, "showerror", lambda title, msg: errors.append(msg))
    app.filename_var.set("../escaped")
    app._save_drawing()
    assert errors
    assert not (tmp_path / "escaped.txt").exists()

    app.filename_var.set("ok")
    app._save_drawing()
    assert (tmp_path / "data" / "ok.txt").exists()


def _cell_fill(app, r: int, c: int) -> str:
    return app.canvas.itemcget(f"cell_{r}_{c}", "fill")


def test_level_picker_paints_selected_level(app):
    app.level_var.set(3)
    app._on_canvas_click(_event(1, 0))
    app._on_canvas_drag(_event(1, 1))
    assert app.grid[1][:3] == [3, 3, 0]
    assert _cell_fill(app, 1, 0) == gui.LEVEL_COLORS[3]
    # Clicking a cell that already has the selected level erases (and the drag erases too).
    app._on_canvas_click(_event(1, 0))
    app._on_canvas_drag(_event(1, 1))
    assert app.grid[1][:2] == [0, 0]
    assert _cell_fill(app, 1, 0) == gui.EMPTY_COLOR


def test_clicking_other_level_repaints_instead_of_erasing(app):
    app.level_var.set(1)
    app._on_canvas_click(_event(2, 2))
    app.level_var.set(4)
    app._on_canvas_click(_event(2, 2))
    assert app.grid[2][2] == 4


def test_levels_round_trip_through_save_and_load(app, monkeypatch):
    logs: list[str] = []
    monkeypatch.setattr(app, "_log", logs.append)
    for level, col in ((1, 0), (2, 1), (3, 2), (4, 3)):
        app.level_var.set(level)
        app._on_canvas_click(_event(0, col))
    saved = [row[:] for row in app.grid]
    app.filename_var.set("levels")
    app._save_drawing()

    app._clear_grid()
    app._populate_drawings_list()
    app.drawings_list.selection_set(0)
    app._load_selected()
    assert app.grid == saved
    assert app.grid[0][:4] == [1, 2, 3, 4]
    assert not any("intensity" in line for line in logs)


def test_levels_above_four_are_kept_and_shown_darkest(app, tmp_path):
    path = gui.DATA_DIR / "deep.txt"
    path.write_text("9\n" * 7, encoding="utf-8")
    app._populate_drawings_list()
    app.drawings_list.selection_set(0)
    app._load_selected()
    assert app.grid[0] == [9]
    assert _cell_fill(app, 0, 0) == gui.LEVEL_COLORS[4]
