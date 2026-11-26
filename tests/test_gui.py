"""The Tk editor.

pytest-xvfb starts a virtual X display where Xvfb is installed (Linux and CI).
Without a display these tests are skipped locally but fail on CI, so they cannot
silently stop running there.
"""

import os
import tkinter as tk
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import git
import pytest

from github_pixel_artworks import gui
from github_pixel_artworks.config import (
    ACTIONS_PANE_MIN_WIDTH,
    DAYS_PER_WEEK,
    DEFAULT_COLUMNS,
    DRAWINGS_PANE_MIN_WIDTH,
    EDITOR_PANE_MIN_WIDTH,
    EMPTY_COLOR,
    GENERATE_BUTTON_TEXT,
    LEVEL_COLORS,
    MAX_CELL_SIZE,
    MAX_WEEKS,
    MIN_CELL_SIZE,
    PATTERN_TETRIS,
    PATTERN_TEXT,
    STATUS_HINT,
    TARGET_CLONE_DIR_NAME,
    WINDOW_SCREEN_MARGIN,
    WINDOW_SIZE,
)
from github_pixel_artworks.patterns import GENERATORS, generate

LOG_MIN_HEIGHT = 40  # pixels: a few lines of the Log stay readable


def new_root() -> tk.Tk:
    try:
        return tk.Tk()
    except tk.TclError:
        if os.environ.get("CI"):
            pytest.fail("Tk could not start on CI: the virtual display (pytest-xvfb) is missing")
        pytest.skip("no display available for Tk")


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[gui.PixelArtGUI]:
    root = new_root()
    root.withdraw()
    monkeypatch.setattr(gui, "DATA_DIR", tmp_path / "data")
    yield gui.PixelArtGUI(root)
    root.destroy()


@pytest.fixture
def window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[gui.PixelArtGUI]:
    """The editor shown on screen, as a user sees it."""
    root = new_root()
    monkeypatch.setattr(gui, "DATA_DIR", tmp_path / "data")
    app = gui.PixelArtGUI(root)
    settle(root)
    yield app
    root.destroy()


def settle(root: tk.Tk) -> None:
    """Let Tk map the window and finish every pending layout pass."""
    for _ in range(5):
        root.update_idletasks()
        root.update()


def resize(app: gui.PixelArtGUI, width: int, height: int) -> None:
    app.root.geometry(f"{width}x{height}")
    settle(app.root)


def pane_widths(app: gui.PixelArtGUI) -> tuple[int, int, int]:
    """Widths of the drawings, editor and actions panes."""
    drawings, editor, actions = (app._panes.nametowidget(name) for name in app._panes.panes())
    return drawings.winfo_width(), editor.winfo_width(), actions.winfo_width()


def at(app: gui.PixelArtGUI, row: int, column: int) -> tk.Event:
    """A fake mouse event inside the given cell."""
    event = SimpleNamespace(x=column * app.cell_size + 1, y=row * app.cell_size + 1)
    return cast(tk.Event, event)


def paint(app: gui.PixelArtGUI, level: int, row: int, column: int) -> None:
    app.level_var.set(level)
    app._on_canvas_click(at(app, row, column))


def cell_fill(app: gui.PixelArtGUI, row: int, column: int) -> str:
    return app.canvas.itemcget(f"cell_{row}_{column}", "fill")


class ImmediateThread:
    """Stands in for threading.Thread and runs the target at once, on this thread."""

    def __init__(self, target: Callable[[], None], daemon: bool) -> None:
        self._target = target

    def start(self) -> None:
        self._target()


def load(app: gui.PixelArtGUI, name: str) -> None:
    app._populate_drawings_list()
    app.drawings_list.selection_set(list(app.drawings_list.get(0, tk.END)).index(name))
    app._load_selected()


class TestPainting:
    def test_drag_paints_the_stroke_value_instead_of_toggling(self, app: gui.PixelArtGUI) -> None:
        app._on_canvas_click(at(app, 0, 0))
        app._on_canvas_drag(at(app, 0, 0))
        app._on_canvas_drag(at(app, 0, 1))

        assert app.grid[0][:3] == [1, 1, 0]

    def test_click_paints_the_selected_level(self, app: gui.PixelArtGUI) -> None:
        paint(app, 3, 1, 0)
        app._on_canvas_drag(at(app, 1, 1))

        assert app.grid[1][:3] == [3, 3, 0]
        assert cell_fill(app, 1, 0) == LEVEL_COLORS[3]

    def test_clicking_a_cell_with_the_selected_level_erases_the_stroke(
        self, app: gui.PixelArtGUI
    ) -> None:
        paint(app, 3, 1, 0)
        app._on_canvas_drag(at(app, 1, 1))

        paint(app, 3, 1, 0)
        app._on_canvas_drag(at(app, 1, 1))

        assert app.grid[1][:2] == [0, 0]
        assert cell_fill(app, 1, 0) == EMPTY_COLOR

    def test_clicking_with_another_level_repaints(self, app: gui.PixelArtGUI) -> None:
        paint(app, 1, 2, 2)

        paint(app, 4, 2, 2)

        assert app.grid[2][2] == 4

    def test_columns_can_be_added_and_removed_within_limits(self, app: gui.PixelArtGUI) -> None:
        assert app.columns == DEFAULT_COLUMNS
        paint(app, 2, 0, 9)

        app._resize_grid(app.columns + 1)
        assert app.columns == MAX_WEEKS
        assert app.grid[0][9] == 2

        app._resize_grid(app.columns - 1)
        assert app.columns == MAX_WEEKS - 1
        assert app.grid[0][9] == 2

        app._resize_grid(app.columns + 1)
        assert app.columns == MAX_WEEKS

        app._resize_grid(1)
        assert app.columns == gui.MIN_COLUMNS

    def test_new_starts_a_year_of_weeks(self, app: gui.PixelArtGUI) -> None:
        app._resize_grid(gui.MIN_COLUMNS)
        assert app.columns == gui.MIN_COLUMNS

        app._new_grid()

        assert app.columns == DEFAULT_COLUMNS
        assert DEFAULT_COLUMNS == MAX_WEEKS


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


class TestGenerateAndPush:
    @pytest.fixture
    def answers(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Say yes to every question and record the error dialogs shown."""
        errors: list[str] = []
        monkeypatch.setattr(gui.messagebox, "askyesno", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(gui.messagebox, "showerror", lambda _title, text: errors.append(text))
        monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)
        return errors

    def test_the_art_branch_is_off_by_default(self, app: gui.PixelArtGUI) -> None:
        assert app.use_art_branch_var.get() is False

    def test_generate_asks_for_the_target_repository_first(
        self, app: gui.PixelArtGUI, answers: list[str]
    ) -> None:
        app.target_repo_var.set("  ")

        app._on_generate_clicked()

        assert answers and "target repository" in answers[0]

    def test_generate_draws_on_the_default_branch_and_push_publishes_it(
        self, app: gui.PixelArtGUI, answers: list[str], git_repo: git.Repo, tmp_path: Path
    ) -> None:
        remote = git.Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
        git_repo.remotes.origin.set_url(str(tmp_path / "origin.git"))
        app.target_repo_var.set(str(git_repo.working_tree_dir))
        app.year_var.set(2026)
        paint(app, 2, 0, 0)

        app._on_generate_clicked()
        app._drain_queues()
        app._on_push_clicked()
        app._drain_queues()

        assert answers == []
        assert len(list(git_repo.iter_commits("main"))) == 1 + 2
        assert remote.heads.main.commit == git_repo.heads.main.commit

    def test_push_publishes_a_url_target_and_removes_its_clone(
        self,
        app: gui.PixelArtGUI,
        answers: list[str],
        empty_remote: str,
        git_identity: None,
        clone_root: Path,
    ) -> None:
        app.target_repo_var.set(empty_remote)
        app.year_var.set(2026)
        paint(app, 2, 0, 0)

        app._on_generate_clicked()
        app._drain_queues()
        parent = clone_root / TARGET_CLONE_DIR_NAME
        assert list(parent.iterdir()) and all(path.is_dir() for path in parent.iterdir())
        app._on_push_clicked()
        app._drain_queues()

        remote = git.Repo(empty_remote.removeprefix("file://"))
        assert answers == []
        assert len(list(remote.iter_commits("main"))) == 2
        assert not parent.exists()
        assert str(app.push_button.cget("state")) == tk.DISABLED

    def test_dry_run_reports_the_plan_without_committing(
        self, app: gui.PixelArtGUI, answers: list[str], git_repo: git.Repo
    ) -> None:
        head = git_repo.head.commit
        app.target_repo_var.set(str(git_repo.working_tree_dir))
        app.year_var.set(2026)
        paint(app, 2, 0, 0)

        app._on_generate_clicked(dry_run=True)
        app._drain_queues()

        assert answers == []
        assert git_repo.head.commit == head
        assert "Dry run: would create 2 commits" in app.log_text.get("1.0", tk.END)
        assert str(app.push_button.cget("state")) == tk.DISABLED


class TestLayout:
    @pytest.mark.parametrize(("width", "height"), [(1024, 420), (1600, 900), (1920, 1080)])
    def test_every_pane_is_visible_after_startup(
        self, window: gui.PixelArtGUI, width: int, height: int
    ) -> None:
        resize(window, width, height)

        drawings, editor, actions = pane_widths(window)

        assert actions >= ACTIONS_PANE_MIN_WIDTH
        assert editor >= EDITOR_PANE_MIN_WIDTH
        assert drawings >= DRAWINGS_PANE_MIN_WIDTH
        assert drawings + editor + actions <= window._panes.winfo_width()

    def test_shrinking_the_window_keeps_the_actions_pane(self, window: gui.PixelArtGUI) -> None:
        resize(window, 1920, 1080)

        resize(window, 1024, 420)

        assert pane_widths(window)[2] >= ACTIONS_PANE_MIN_WIDTH

    def test_growing_the_window_widens_only_the_grid(self, window: gui.PixelArtGUI) -> None:
        resize(window, 1024, 420)
        drawings, editor, actions = pane_widths(window)

        resize(window, 1920, 1080)

        assert pane_widths(window)[0] == drawings
        assert pane_widths(window)[1] > editor
        assert pane_widths(window)[2] == actions

    def test_fit_mode_sizes_square_cells_so_a_year_fills_the_canvas_width(
        self, window: gui.PixelArtGUI
    ) -> None:
        window._resize_grid(MAX_WEEKS)
        resize(window, *WINDOW_SIZE)

        canvas_width = window.canvas.winfo_width()
        canvas_height = window.canvas.winfo_height()
        coords = window.canvas.coords("cell_0_0")
        size = coords[2] - coords[0]
        assert size == coords[3] - coords[1]
        assert size == window.cell_size
        weeks = MAX_WEEKS
        assert MAX_WEEKS * size <= canvas_width
        assert abs(size - (canvas_width - 2) // weeks) <= 1
        assert DAYS_PER_WEEK * size < canvas_height
        assert window.canvas.xview() == (0.0, 1.0)
        assert window._fit_to_width

    def test_the_cell_size_control_zooms_the_grid_and_leaves_fit_mode(
        self, window: gui.PixelArtGUI
    ) -> None:
        resize(window, *WINDOW_SIZE)
        original = window.cell_size

        window.cell_size_var.set(MIN_CELL_SIZE)
        settle(window.root)

        assert window._fit_to_width is False
        assert window.cell_size == MIN_CELL_SIZE
        assert window.cell_size < original
        coords = window.canvas.coords("cell_0_0")
        assert coords[2] - coords[0] == MIN_CELL_SIZE

    def test_fit_keeps_a_full_year_visible_when_the_window_resizes(
        self, window: gui.PixelArtGUI
    ) -> None:
        window._resize_grid(MAX_WEEKS)
        resize(window, 1600, 900)
        size_at_1600 = window.cell_size
        assert window.canvas.xview() == (0.0, 1.0)

        resize(window, *WINDOW_SIZE)
        assert window._fit_to_width
        assert window.cell_size > size_at_1600
        assert window.canvas.xview() == (0.0, 1.0)

    def test_fit_restores_width_fit_after_a_manual_zoom(self, window: gui.PixelArtGUI) -> None:
        window._resize_grid(MAX_WEEKS)
        resize(window, *WINDOW_SIZE)
        window.cell_size_var.set(MAX_CELL_SIZE)
        settle(window.root)
        assert window.canvas.xview() != (0.0, 1.0)

        window._fit_to_canvas()
        settle(window.root)

        assert window._fit_to_width
        assert window.canvas.xview() == (0.0, 1.0)

    def test_fit_accounts_for_offset_and_added_weeks(self, window: gui.PixelArtGUI) -> None:
        window._resize_grid(MAX_WEEKS)
        resize(window, *WINDOW_SIZE)
        size_for_a_year = window.cell_size

        window.offset_var.set(20)
        window._on_schedule_changed()
        settle(window.root)

        assert window._weeks_to_fit() == MAX_WEEKS + 20
        assert window.cell_size < size_for_a_year
        assert window.canvas.xview() == (0.0, 1.0)

    def test_the_default_window_fits_a_1080p_screen(self) -> None:
        assert WINDOW_SIZE[0] + WINDOW_SCREEN_MARGIN <= 1920
        assert WINDOW_SIZE[1] + WINDOW_SCREEN_MARGIN <= 1080

    def test_a_full_year_on_a_small_window_scrolls_instead_of_hiding_actions(
        self, window: gui.PixelArtGUI
    ) -> None:
        resize(window, 1024, 420)

        window._resize_grid(MAX_WEEKS)
        settle(window.root)

        assert pane_widths(window)[2] >= ACTIONS_PANE_MIN_WIDTH
        assert window.canvas.xview() != (0.0, 1.0)

    def test_the_generate_button_is_labelled_generate_commits(
        self, window: gui.PixelArtGUI
    ) -> None:
        assert str(window.generate_button.cget("text")) == GENERATE_BUTTON_TEXT
        assert window.status_var.get() == STATUS_HINT

    def test_every_action_and_the_log_fit_a_small_window(self, window: gui.PixelArtGUI) -> None:
        resize(window, 1024, 420)
        bottom = window.root.winfo_rooty() + window.root.winfo_height()

        for widget in (
            window.generate_button,
            window.push_button,
            window.force_button,
            window.log_text,
        ):
            assert widget.winfo_ismapped()
            assert widget.winfo_rooty() + widget.winfo_height() <= bottom
        assert window.log_text.winfo_height() >= LOG_MIN_HEIGHT

    def test_the_art_branch_row_only_shows_when_enabled(self, window: gui.PixelArtGUI) -> None:
        assert not window.art_branch_details.winfo_ismapped()

        window.use_art_branch_var.set(True)
        window._toggle_art_branch()
        settle(window.root)

        assert window.art_branch_details.winfo_ismapped()

    def test_the_first_size_fits_a_small_screen(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = new_root()
        monkeypatch.setattr(gui, "DATA_DIR", tmp_path / "data")
        monkeypatch.setattr(root, "winfo_screenwidth", lambda: 1024)
        monkeypatch.setattr(root, "winfo_screenheight", lambda: 600)

        app = gui.PixelArtGUI(root)
        settle(root)

        assert root.winfo_width() <= 1024
        assert root.winfo_height() <= 600
        assert pane_widths(app)[2] >= ACTIONS_PANE_MIN_WIDTH
        root.destroy()


class TestTargetDefault:
    def test_prefills_the_detected_profile_repository(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, set_global_git_config
    ) -> None:
        set_global_git_config("github.user", "octocat")
        monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(gui, "DATA_DIR", tmp_path / "data")
        root = new_root()
        root.withdraw()

        app = gui.PixelArtGUI(root)
        app._drain_queues()

        assert app.target_repo_var.get() == "https://github.com/octocat/octocat"
        assert "git config github.user" in app.log_text.get("1.0", tk.END)
        root.destroy()

    def test_stays_empty_when_nothing_is_detected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gui.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(gui, "DATA_DIR", tmp_path / "data")
        root = new_root()
        root.withdraw()

        app = gui.PixelArtGUI(root)
        app._drain_queues()

        assert app.target_repo_var.get() == ""
        root.destroy()


class TestPatternControls:
    def test_generate_pattern_fills_the_grid_and_keeps_it_editable(
        self, app: gui.PixelArtGUI
    ) -> None:
        app.pattern_var.set(PATTERN_TETRIS)
        app._pattern_seed = 11
        app._resize_grid(20)

        app._on_generate_pattern()

        assert app.grid == generate(PATTERN_TETRIS, width=20, seed=11)
        assert "Pattern 'tetris' (seed 11)" in app.log_text.get("1.0", tk.END)
        paint(app, 4, 0, 0)
        assert app.grid[0][0] == 4

    def test_new_seed_draws_a_different_grid(self, app: gui.PixelArtGUI) -> None:
        app.pattern_var.set(PATTERN_TETRIS)
        app._resize_grid(16)
        app._on_generate_pattern()
        first = [row[:] for row in app.grid]
        first_seed = app._pattern_seed

        app._on_generate_pattern(new_seed=True)

        assert app._pattern_seed != first_seed
        assert app.grid == generate(PATTERN_TETRIS, width=16, seed=app._pattern_seed)
        assert app.grid != first

    def test_text_pattern_widens_the_grid_to_fit(self, app: gui.PixelArtGUI) -> None:
        app._resize_grid(gui.MIN_COLUMNS)
        app.pattern_var.set(PATTERN_TEXT)
        app.pattern_text_var.set("SIMONE")

        app._on_generate_pattern()

        expected = generate(PATTERN_TEXT, width=35, seed=app._pattern_seed, text="SIMONE")
        assert app.columns == 35
        assert app.grid == expected

    def test_text_pattern_without_text_explains_the_problem(
        self, app: gui.PixelArtGUI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        errors: list[str] = []
        monkeypatch.setattr(gui.messagebox, "showerror", lambda _title, msg: errors.append(msg))
        app.pattern_var.set(PATTERN_TEXT)
        app.pattern_text_var.set("")
        empty = [row[:] for row in app.grid]

        app._on_generate_pattern()

        assert errors
        assert "text" in errors[0].lower()
        assert app.grid == empty

    def test_the_combobox_fits_the_longest_pattern_name(self, app: gui.PixelArtGUI) -> None:
        longest = max(len(name) for name in GENERATORS)
        assert int(app.pattern_combo.cget("width")) >= longest

    def test_the_text_field_shows_only_for_the_text_pattern(self, window: gui.PixelArtGUI) -> None:
        assert window.pattern_var.get() != PATTERN_TEXT
        assert not window.pattern_text_entry.winfo_ismapped()

        window.pattern_var.set(PATTERN_TEXT)
        window._toggle_pattern_text()
        settle(window.root)

        assert window.pattern_text_entry.winfo_ismapped()
