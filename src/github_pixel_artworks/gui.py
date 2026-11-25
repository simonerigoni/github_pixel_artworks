#!/usr/bin/env python
"""
github-pixel-artworks GUI

Interactive editor for creating 7-row pixel art grids (for GitHub contribution graphs).

- Click cells to toggle filled/empty.
- Add/remove week columns.
- Select year (auto positions to first Sunday of the year).
- Save .txt files to the data/ folder (compatible with the CLI).
- "Generate Art" button: creates the backdated commits for the selected year (in-place).
  The "Use dedicated art branch" checkbox (on by default) tells the core to auto-manage
  stashing + switching to the branch (and back afterwards). The suggested branch name
  is "artworks-<year>" (e.g. artworks-2016) so each year's art lives on its own branch.
- "Push to GitHub" button: pushes the branch that received the art commits.

Launch:
    python gui.py
    # or after `uv sync` / install:
    github-pixel-artworks-gui
"""

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import git

from .core import (
    MAX_WEEKS,
    apply_drawing,
    drawing_path,
    get_first_sunday_of_year,
    load_grid,
    save_grid,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data")
CELL_SIZE = 18
EMPTY_COLOR = "#ebedf0"
FILLED_COLOR = "#40c463"  # GitHub-like green for level 1
GRID_BG = "#f0f0f0"

MIN_COLS = 3
MAX_COLS = MAX_WEEKS


# ---------------------------------------------------------------------------
# Main GUI Class
# ---------------------------------------------------------------------------


class PixelArtGUI:
    """Tkinter editor: draw a 7-row grid, save it to data/, generate and push the art."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("GitHub Pixel Artworks - Drawer")
        root.geometry("900x620")
        root.minsize(700, 500)

        # Internal state: 7 rows x N cols, values 0 or 1 (for v1)
        self.grid: list[list[int]] = [[0] * 10 for _ in range(7)]
        self.current_cols = 10

        # Value painted while dragging (set by the click that starts the stroke)
        self._paint_value = 1
        # Branch that received the last generated art (what "Push" pushes)
        self._art_target_branch: str | None = None

        # For thread <-> GUI communication: worker threads never touch Tk directly,
        # they enqueue log lines and UI callbacks that the main thread drains.
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.ui_queue: queue.Queue[Callable[[], object]] = queue.Queue()

        # Make sure data dir exists before listing it
        DATA_DIR.mkdir(exist_ok=True)

        self._build_ui()
        self._refresh_canvas()
        self._populate_drawings_list()
        self._update_preview_label()
        self._update_art_branch_suggestion()

        # Poll the log queue periodically
        self.root.after(80, self._poll_log_queue)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Top control bar
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Year:").pack(side=tk.LEFT)
        self.year_var = tk.IntVar(value=date.today().year)
        year_spin = ttk.Spinbox(
            top,
            from_=2010,
            to=2035,
            textvariable=self.year_var,
            width=6,
            command=self._on_params_changed,
        )
        year_spin.pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(top, text="Offset weeks:").pack(side=tk.LEFT)
        self.offset_var = tk.IntVar(value=0)
        offset_spin = ttk.Spinbox(
            top,
            from_=0,
            to=MAX_WEEKS,
            textvariable=self.offset_var,
            width=4,
            command=self._on_params_changed,
        )
        offset_spin.pack(side=tk.LEFT, padx=(2, 12))

        ttk.Button(top, text="New", command=self._new_grid).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Add week", command=lambda: self._change_cols(+1)).pack(side=tk.LEFT)
        ttk.Button(top, text="Remove week", command=lambda: self._change_cols(-1)).pack(
            side=tk.LEFT
        )
        ttk.Button(top, text="Clear", command=self._clear_grid).pack(side=tk.LEFT, padx=4)

        # Main area: left = drawings list, center = editor, right = actions
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Left: saved drawings
        left_frame = ttk.LabelFrame(main_pane, text="Saved in data/", padding=6)
        main_pane.add(left_frame, weight=1)

        self.drawings_list = tk.Listbox(left_frame, height=12, exportselection=False)
        self.drawings_list.pack(fill=tk.BOTH, expand=True)
        self.drawings_list.bind("<Double-Button-1>", lambda e: self._load_selected())

        btns = ttk.Frame(left_frame)
        btns.pack(fill=tk.X, pady=4)
        ttk.Button(btns, text="Load", command=self._load_selected).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        ttk.Button(btns, text="Delete", command=self._delete_selected).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        ttk.Button(btns, text="Refresh", command=self._populate_drawings_list).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )

        # Center: the editor canvas + preview
        center = ttk.Frame(main_pane)
        main_pane.add(center, weight=3)

        self.canvas = tk.Canvas(
            center, bg=GRID_BG, highlightthickness=1, highlightbackground="#888"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)

        self.preview_label = ttk.Label(center, text="", font=("TkDefaultFont", 9))
        self.preview_label.pack(anchor=tk.W, padx=4)

        # Right: actions + log
        right = ttk.Frame(main_pane)
        main_pane.add(right, weight=2)

        action_frame = ttk.LabelFrame(right, text="Actions (this repo)", padding=6)
        action_frame.pack(fill=tk.X, pady=(0, 6))

        self.filename_var = tk.StringVar(value="my_art")
        ttk.Label(action_frame, text="Filename (no .txt):").pack(anchor=tk.W)
        ttk.Entry(action_frame, textvariable=self.filename_var).pack(fill=tk.X, pady=2)

        ttk.Button(action_frame, text="Save to data/", command=self._save_drawing).pack(
            fill=tk.X, pady=2
        )

        ttk.Separator(action_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # Dedicated art branch support (highly recommended for this repo)
        self.use_art_branch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            action_frame,
            text="Use dedicated art branch (avoids dirty errors)",
            variable=self.use_art_branch_var,
        ).pack(anchor=tk.W)

        # Start with a year-specific branch name per user preference (artworks-2016, artworks-2025, ...)
        year_for_branch = self.year_var.get()
        self.art_branch_var = tk.StringVar(value=f"artworks-{year_for_branch}")
        branch_frame = ttk.Frame(action_frame)
        ttk.Label(branch_frame, text="Art branch name:").pack(side=tk.LEFT)
        ttk.Entry(branch_frame, textvariable=self.art_branch_var, width=18).pack(
            side=tk.LEFT, padx=4
        )
        branch_frame.pack(fill=tk.X, pady=2)

        self.generate_btn = ttk.Button(
            action_frame, text="Generate Art for Selected Year", command=self._on_generate_clicked
        )
        self.generate_btn.pack(fill=tk.X, pady=2)

        self.push_btn = ttk.Button(
            action_frame, text="Push to GitHub", command=self._on_push_clicked, state=tk.DISABLED
        )
        self.push_btn.pack(fill=tk.X, pady=2)

        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            action_frame,
            text="Force (ignore dirty tree warning — advanced)",
            variable=self.force_var,
        ).pack(anchor=tk.W, pady=(4, 0))

        # Log area
        log_frame = ttk.LabelFrame(right, text="Log", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = ScrolledText(log_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.status_var = tk.StringVar(
            value="Ready - draw on the grid, pick year, use dedicated branch option, then Generate + Push"
        )
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, padding=2).pack(
            fill=tk.X, side=tk.BOTTOM
        )

    # ------------------------------------------------------------------
    # Canvas / Grid drawing
    # ------------------------------------------------------------------

    def _refresh_canvas(self) -> None:
        self.canvas.delete("all")
        rows = 7
        cols = self.current_cols
        w = CELL_SIZE
        h = CELL_SIZE

        for r in range(rows):
            for c in range(cols):
                x0 = c * w
                y0 = r * h
                x1 = x0 + w
                y1 = y0 + h
                fill = FILLED_COLOR if self.grid[r][c] > 0 else EMPTY_COLOR
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill=fill, outline="#999", tags=(f"cell_{r}_{c}",)
                )

        # size the canvas
        self.canvas.config(width=cols * w + 2, height=rows * h + 2)

    def _cell_at(self, x: int, y: int) -> tuple[int, int] | None:
        r, c = y // CELL_SIZE, x // CELL_SIZE
        if 0 <= r < 7 and 0 <= c < self.current_cols:
            return r, c
        return None

    def _on_canvas_click(self, event: tk.Event) -> None:
        # A click toggles its cell and sets the value the rest of the drag paints.
        cell = self._cell_at(event.x, event.y)
        if cell is None:
            return
        r, c = cell
        self._paint_value = 0 if self.grid[r][c] else 1
        self._set_cell(r, c, self._paint_value)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        # Dragging paints (instead of toggling on every motion event, which flickered).
        cell = self._cell_at(event.x, event.y)
        if cell is not None:
            self._set_cell(*cell, self._paint_value)

    def _set_cell(self, r: int, c: int, value: int) -> None:
        if self.grid[r][c] == value:
            return
        self.grid[r][c] = value
        self._refresh_canvas()
        self._update_preview_label()

    def _change_cols(self, delta: int) -> None:
        new_cols = max(MIN_COLS, min(MAX_COLS, self.current_cols + delta))
        if new_cols == self.current_cols:
            return
        old_cols = self.current_cols
        self.current_cols = new_cols

        if new_cols > old_cols:
            # add columns of zeros
            for r in range(7):
                self.grid[r].extend([0] * (new_cols - old_cols))
        else:
            # truncate
            for r in range(7):
                self.grid[r] = self.grid[r][:new_cols]

        self._refresh_canvas()
        self._update_preview_label()

    def _clear_grid(self) -> None:
        self.grid = [[0] * self.current_cols for _ in range(7)]
        self._refresh_canvas()
        self._update_preview_label()

    def _new_grid(self) -> None:
        self.current_cols = 10
        self.grid = [[0] * self.current_cols for _ in range(7)]
        self.filename_var.set("new_drawing")
        self._refresh_canvas()
        self._update_preview_label()

    # ------------------------------------------------------------------
    # Preview / params
    # ------------------------------------------------------------------

    def _on_params_changed(self) -> None:
        self._update_preview_label()
        self._update_art_branch_suggestion()

    def _update_preview_label(self) -> None:
        try:
            year = self.year_var.get()
            offset = self.offset_var.get()
            start = get_first_sunday_of_year(year) + timedelta(weeks=offset)
            w = self.current_cols
            end = start + timedelta(weeks=w - 1, days=6)
            total = sum(sum(row) for row in self.grid)  # multiplier=1 for preview
            self.preview_label.config(
                text=f"Year {year} +{offset}w → starts {start.date()} (Sun), ends {end.date()}, ~{total} commits"
            )
        except tk.TclError, ValueError, OverflowError:
            self.preview_label.config(text="Invalid year/offset")

    def _update_art_branch_suggestion(self) -> None:
        """Keep the art branch name in sync with the selected year (user preference:
        use year-specific branches like 'artworks-2016' instead of a single 'artworks').
        Only auto-updates if the field still looks like a generated suggestion.
        """
        try:
            year = self.year_var.get()
        except tk.TclError:  # spinbox temporarily holds a non-number
            return
        current = self.art_branch_var.get().strip()
        if not current or current.startswith("artworks-") or current == "artworks":
            self.art_branch_var.set(f"artworks-{year}")

    # ------------------------------------------------------------------
    # Data (drawings) list & load/save
    # ------------------------------------------------------------------

    def _populate_drawings_list(self) -> None:
        self.drawings_list.delete(0, tk.END)
        if not DATA_DIR.exists():
            return
        for p in sorted(DATA_DIR.glob("*.txt")):
            self.drawings_list.insert(tk.END, p.name)

    def _load_selected(self) -> None:
        sel = self.drawings_list.curselection()
        if not sel:
            return
        name = self.drawings_list.get(sel[0])
        path = DATA_DIR / name
        try:
            loaded = load_grid(path)
            if any(v > 1 for row in loaded for v in row):
                self._log(
                    f"Note: {name} uses intensity levels; the editor shows them as on/off "
                    "and saving will store them as level 1."
                )
            self.grid = [[1 if v > 0 else 0 for v in row] for row in loaded]
            self.current_cols = len(self.grid[0]) if self.grid else 10
            self.filename_var.set(Path(name).stem)
            self._refresh_canvas()
            self._update_preview_label()
            self._log(f"Loaded {name}")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _delete_selected(self) -> None:
        sel = self.drawings_list.curselection()
        if not sel:
            return
        name = self.drawings_list.get(sel[0])
        if not messagebox.askyesno("Delete", f"Delete {name}?"):
            return
        try:
            drawing_path(DATA_DIR, name).unlink(missing_ok=True)
        except (OSError, ValueError) as e:
            messagebox.showerror("Delete error", str(e))
        self._populate_drawings_list()

    def _save_drawing(self) -> None:
        try:
            path = drawing_path(DATA_DIR, self.filename_var.get())
            save_grid(path, self.grid)
            self._log(f"Saved to {path}")
            self._populate_drawings_list()
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    # ------------------------------------------------------------------
    # Generate + Push (the important buttons)
    # ------------------------------------------------------------------

    def _on_generate_clicked(self) -> None:
        if not messagebox.askyesno(
            "Generate Art",
            "This will create backdated commits in the current repository\n"
            "(this repo is your dedicated pixel-art canvas).\n\nContinue?",
        ):
            return

        self.generate_btn.config(state=tk.DISABLED)
        self.push_btn.config(state=tk.DISABLED)
        self.status_var.set("Generating...")

        try:
            year = self.year_var.get()
            offset = self.offset_var.get()
        except tk.TclError:
            messagebox.showerror("Generate Art", "Year and offset must be whole numbers.")
            self.generate_btn.config(state=tk.NORMAL)
            self.status_var.set("Ready")
            return
        art_branch = self.art_branch_var.get().strip() if self.use_art_branch_var.get() else None
        # Read Tk variables here: worker threads must not touch Tk objects.
        force = self.force_var.get()

        def worker() -> None:
            try:
                n = apply_drawing(
                    grid=self.grid,
                    year=year,
                    offset_weeks=offset,
                    target_repo=".",
                    in_place=True,
                    force=force,
                    art_branch=art_branch,
                    log=self._queue_log,
                )
                target = art_branch or _active_branch(git.Repo("."))
                self._call_in_ui(lambda: setattr(self, "_art_target_branch", target))
                where = f" on branch {target}" if target else ""
                self._queue_log(f"\n=== SUCCESS: {n} commits created for year {year}{where} ===")
                if target:
                    self._call_in_ui(lambda: self.push_btn.config(state=tk.NORMAL))
            except Exception as e:  # show any failure in the log instead of killing the thread
                self._queue_log(f"\nError: {e}")
            finally:
                self._call_in_ui(lambda: self.generate_btn.config(state=tk.NORMAL))
                self._call_in_ui(lambda: self.status_var.set("Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_push_clicked(self) -> None:
        branch = self._art_target_branch
        if not branch:
            return
        self.push_btn.config(state=tk.DISABLED)
        self.status_var.set("Pushing...")

        def worker() -> None:
            try:
                self._queue_log(f"Pushing {branch} ...")
                git.Repo(".").git.push("origin", branch)
                self._queue_log("Push completed successfully.")
            except Exception as e:  # show any failure in the log instead of killing the thread
                self._queue_log(f"Push error: {e}")
            finally:
                self._call_in_ui(lambda: self.status_var.set("Ready"))
                # Re-enable push in case user wants to retry
                self._call_in_ui(lambda: self.push_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Logging helpers (thread safe)
    # ------------------------------------------------------------------

    def _queue_log(self, msg: str) -> None:
        self.log_queue.put(msg)

    def _call_in_ui(self, func: Callable[[], object]) -> None:
        """Run ``func`` on the Tk main thread (safe to call from worker threads)."""
        self.ui_queue.put(func)

    def _poll_log_queue(self) -> None:
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(msg)
        while True:
            try:
                func = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            func()
        self.root.after(80, self._poll_log_queue)

    def _append_log(self, text: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _log(self, text: str) -> None:
        """Log from the main thread."""
        self._append_log(text)


def _active_branch(repo: git.Repo) -> str | None:
    """Current branch name, or None when HEAD is detached."""
    return None if repo.head.is_detached else repo.active_branch.name


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point of the ``github-pixel-artworks-gui`` command."""
    root = tk.Tk()
    PixelArtGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
