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
  stashing + checkout -B the branch (default name "artworks") so you avoid dirty-repo errors.
- "Push to GitHub" button: pushes the current (art) branch after generation.

Launch:
    python gui.py
    # or after `uv sync` / install:
    github-pixel-artworks-gui
"""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from pathlib import Path

from .core import (
    apply_drawing,
    load_grid,
    save_grid,
    get_first_sunday_of_year,
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
MAX_COLS = 60


# ---------------------------------------------------------------------------
# Main GUI Class
# ---------------------------------------------------------------------------


class PixelArtGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("GitHub Pixel Artworks - Drawer")
        root.geometry("900x620")
        root.minsize(700, 500)

        # Internal state: 7 rows x N cols, values 0 or 1 (for v1)
        self.grid: list[list[int]] = [[0] * 10 for _ in range(7)]
        self.current_cols = 10

        # For thread <-> GUI communication
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self._refresh_canvas()
        self._populate_drawings_list()
        self._update_preview_label()

        # Poll the log queue periodically
        self.root.after(80, self._poll_log_queue)

        # Make sure data dir exists
        DATA_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Top control bar
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Year:").pack(side=tk.LEFT)
        self.year_var = tk.IntVar(value=2025)
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
            to=52,
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

        self.art_branch_var = tk.StringVar(value="artworks")
        branch_frame = ttk.Frame(action_frame)
        ttk.Label(branch_frame, text="Art branch name:").pack(side=tk.LEFT)
        ttk.Entry(branch_frame, textvariable=self.art_branch_var, width=15).pack(
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

    def _refresh_canvas(self):
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
                rect = self.canvas.create_rectangle(
                    x0, y0, x1, y1, fill=fill, outline="#999", tags=f"cell_{r}_{c}"
                )
                # store row/col on the item for hit testing
                self.canvas.itemconfig(rect, tags=(f"cell_{r}_{c}", str(r), str(c)))

        # size the canvas
        self.canvas.config(width=cols * w + 2, height=rows * h + 2)

    def _on_canvas_click(self, event):
        self._toggle_cell_at(event.x, event.y)

    def _on_canvas_drag(self, event):
        self._toggle_cell_at(event.x, event.y)

    def _toggle_cell_at(self, x: int, y: int):
        w = CELL_SIZE
        c = x // w
        r = y // w
        if 0 <= r < 7 and 0 <= c < self.current_cols:
            self.grid[r][c] = 1 if self.grid[r][c] == 0 else 0
            self._refresh_canvas()
            self._update_preview_label()

    def _change_cols(self, delta: int):
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

    def _clear_grid(self):
        self.grid = [[0] * self.current_cols for _ in range(7)]
        self._refresh_canvas()
        self._update_preview_label()

    def _new_grid(self):
        self.current_cols = 10
        self.grid = [[0] * self.current_cols for _ in range(7)]
        self.filename_var.set("new_drawing")
        self._refresh_canvas()
        self._update_preview_label()

    # ------------------------------------------------------------------
    # Preview / params
    # ------------------------------------------------------------------

    def _on_params_changed(self):
        self._update_preview_label()

    def _update_preview_label(self):
        try:
            year = self.year_var.get()
            offset = self.offset_var.get()
            start = get_first_sunday_of_year(year) + __import__("datetime").timedelta(weeks=offset)
            w = self.current_cols
            end = start + __import__("datetime").timedelta(weeks=w - 1, days=6)
            total = sum(sum(row) for row in self.grid)  # multiplier=1 for preview
            self.preview_label.config(
                text=f"Year {year} +{offset}w → starts {start.date()} (Sun), ends {end.date()}, ~{total} commits"
            )
        except Exception:
            self.preview_label.config(text="Invalid year/offset")

    # ------------------------------------------------------------------
    # Data (drawings) list & load/save
    # ------------------------------------------------------------------

    def _populate_drawings_list(self):
        self.drawings_list.delete(0, tk.END)
        if not DATA_DIR.exists():
            return
        for p in sorted(DATA_DIR.glob("*.txt")):
            self.drawings_list.insert(tk.END, p.name)

    def _load_selected(self):
        sel = self.drawings_list.curselection()
        if not sel:
            return
        name = self.drawings_list.get(sel[0])
        path = DATA_DIR / name
        try:
            loaded = load_grid(path)
            self.grid = [[1 if v > 0 else 0 for v in row] for row in loaded]
            self.current_cols = len(self.grid[0]) if self.grid else 10
            self.filename_var.set(Path(name).stem)
            self._refresh_canvas()
            self._update_preview_label()
            self._log(f"Loaded {name}")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _delete_selected(self):
        sel = self.drawings_list.curselection()
        if not sel:
            return
        name = self.drawings_list.get(sel[0])
        if not messagebox.askyesno("Delete", f"Delete {name}?"):
            return
        (DATA_DIR / name).unlink(missing_ok=True)
        self._populate_drawings_list()

    def _save_drawing(self):
        name = self.filename_var.get().strip()
        if not name:
            name = "untitled"
        if not name.endswith(".txt"):
            name += ".txt"
        path = DATA_DIR / name
        try:
            save_grid(path, self.grid)
            self._log(f"Saved to {path}")
            self._populate_drawings_list()
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    # ------------------------------------------------------------------
    # Generate + Push (the important buttons)
    # ------------------------------------------------------------------

    def _on_generate_clicked(self):
        if not messagebox.askyesno(
            "Generate Art",
            "This will create backdated commits in the current repository\n"
            "(this repo is your dedicated pixel-art canvas).\n\nContinue?",
        ):
            return

        self.generate_btn.config(state=tk.DISABLED)
        self.push_btn.config(state=tk.DISABLED)
        self.status_var.set("Generating...")

        year = self.year_var.get()
        offset = self.offset_var.get()
        art_branch = self.art_branch_var.get().strip() if self.use_art_branch_var.get() else None

        def worker():
            try:
                n = apply_drawing(
                    grid=self.grid,
                    year=year,
                    offset_weeks=offset,
                    target_repo=".",
                    in_place=True,
                    force=self.force_var.get(),
                    art_branch=art_branch,
                    log=self._queue_log,
                )
                if art_branch:
                    self._queue_log(
                        f"\n=== SUCCESS: {n} commits created for year {year} on branch {art_branch} ==="
                    )
                else:
                    self._queue_log(f"\n=== SUCCESS: {n} commits created for year {year} ===")
                self.root.after(0, lambda: self.push_btn.config(state=tk.NORMAL))
            except Exception as e:
                self._queue_log(f"\nERROR: {e}")
            finally:
                self.root.after(0, lambda: self.generate_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.status_var.set("Ready"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_push_clicked(self):
        self.push_btn.config(state=tk.DISABLED)
        self.status_var.set("Pushing...")

        def worker():
            try:
                import git

                repo = git.Repo(".")
                branch = repo.active_branch.name if not repo.head.is_detached else "HEAD"
                self._queue_log(f"Pushing {branch} ...")
                repo.git.push("origin", branch)
                self._queue_log("Push completed successfully.")
            except Exception as e:
                self._queue_log(f"Push error: {e}")
            finally:
                self.root.after(0, lambda: self.status_var.set("Ready"))
                # Re-enable push in case user wants to retry
                self.root.after(0, lambda: self.push_btn.config(state=tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Logging helpers (thread safe)
    # ------------------------------------------------------------------

    def _queue_log(self, msg: str):
        self.log_queue.put(msg)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_log_queue)

    def _append_log(self, text: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _log(self, text: str):
        # Direct log from main thread
        self._append_log(text)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    root = tk.Tk()
    PixelArtGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
