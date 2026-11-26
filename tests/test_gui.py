"""Smoke tests for the Tk editor (skipped when no display is available, e.g. in CI)."""

import tkinter as tk
from types import SimpleNamespace

import pytest

from github_pixel_artworks import gui


@pytest.fixture
def app(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
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
