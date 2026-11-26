"""Tkinter editor: ``github-pixel-artworks-gui``.

Draw an artwork with GitHub's four shades, save it to ``data/``, then add the
empty, backdated commits for a year to a repository you own and push them. Git
work runs on worker threads, which talk to Tk only through queues drained on the
main thread.
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

from .art_repo import is_remote_url, push_branch, remove_tree
from .artwork import Grid, count_commits, drawing_path, level_color, load_grid, save_grid
from .config import (
    ACTIONS_PANE_MIN_WIDTH,
    ACTIONS_PANE_WIDTH,
    ART_BRANCH_PREFIX,
    CANVAS_BORDER,
    CELL_OUTLINE,
    CELL_SIZE,
    DARK_LEVEL_TEXT_FROM,
    DATA_DIR,
    DAYS_PER_WEEK,
    DEFAULT_COLUMNS,
    DRAWING_BUTTON_WIDTH,
    DRAWINGS_PANE_MIN_WIDTH,
    DRAWINGS_PANE_WIDTH,
    EDITOR_PANE_MIN_WIDTH,
    GRID_BACKGROUND,
    HINT_COLOR,
    HINT_PADDING,
    LEVEL_COLORS,
    LOG_LINES,
    MAX_WEEKS,
    MAX_YEAR,
    MIN_COLUMNS,
    MIN_YEAR,
    QUEUE_POLL_MS,
    STATUS_HINT,
    STATUS_READY,
    WINDOW_MIN_SIZE,
    WINDOW_SCREEN_MARGIN,
    WINDOW_SIZE,
)
from .dates import get_first_sunday_of_year
from .github import detect_github_username, profile_repo_url
from .painter import apply_drawing


class PixelArtGUI:
    """The editor window: drawings list, grid editor, actions and log."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("GitHub Pixel Artworks")
        root.geometry(_first_geometry(root))
        root.minsize(*WINDOW_MIN_SIZE)

        self.grid: Grid = _empty_grid(DEFAULT_COLUMNS)
        self.level_var = tk.IntVar(value=1)
        self._stroke_value = 1
        self._push_target: tuple[Path, str, bool] | None = None
        self._hints: list[ttk.Label] = []
        self._panes_placed = False
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._ui_queue: queue.Queue[Callable[[], object]] = queue.Queue()
        self._detected_users: queue.Queue[tuple[str, str]] = queue.Queue()

        DATA_DIR.mkdir(exist_ok=True)
        self._build_toolbar()
        self._build_panes()
        self._build_status_bar()

        self._redraw()
        self._populate_drawings_list()
        self._suggest_art_branch()
        self._prefill_target_repo()
        self.root.after(QUEUE_POLL_MS, self._drain_queues)

    @property
    def columns(self) -> int:
        """Number of week columns in the grid."""
        return len(self.grid[0])

    # Layout ----------------------------------------------------------------

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill=tk.X)

        self.year_var = tk.IntVar(value=date.today().year)
        self.offset_var = tk.IntVar(value=0)
        self._add_spinbox(bar, "Year:", self.year_var, MIN_YEAR, MAX_YEAR, width=6)
        self._add_spinbox(bar, "Offset weeks:", self.offset_var, 0, MAX_WEEKS, width=4)

        for text, command in (
            ("New", self._new_grid),
            ("Add week", lambda: self._resize_grid(self.columns + 1)),
            ("Remove week", lambda: self._resize_grid(self.columns - 1)),
            ("Clear", self._clear_grid),
        ):
            ttk.Button(bar, text=text, command=command).pack(side=tk.LEFT, padx=2)

        ttk.Label(bar, text="Level:").pack(side=tk.LEFT, padx=(12, 2))
        for level, color in LEVEL_COLORS.items():
            tk.Radiobutton(
                bar,
                text=str(level),
                variable=self.level_var,
                value=level,
                indicatoron=False,
                width=2,
                bg=color,
                activebackground=color,
                selectcolor=color,
                fg="white" if level >= DARK_LEVEL_TEXT_FROM else "black",
                offrelief=tk.FLAT,
                relief=tk.RAISED,
            ).pack(side=tk.LEFT, padx=1)

    def _add_spinbox(
        self, parent: ttk.Frame, label: str, variable: tk.IntVar, low: int, high: int, width: int
    ) -> None:
        ttk.Label(parent, text=label).pack(side=tk.LEFT)
        ttk.Spinbox(
            parent,
            from_=low,
            to=high,
            textvariable=variable,
            width=width,
            command=self._on_schedule_changed,
        ).pack(side=tk.LEFT, padx=(2, 12))

    def _build_panes(self) -> None:
        self._panes = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self._panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        # Only the grid pane has weight, so it alone absorbs window resizes.
        self._panes.add(self._build_drawings_pane(self._panes), weight=0)
        self._panes.add(self._build_editor_pane(self._panes), weight=1)
        self._panes.add(self._build_actions_pane(self._panes), weight=0)
        self._panes.bind("<Configure>", lambda _event: self._fit_panes())
        self._panes.bind("<ButtonRelease-1>", lambda _event: self._fit_panes(), add="+")

    def _build_drawings_pane(self, parent: ttk.PanedWindow) -> ttk.LabelFrame:
        pane = ttk.LabelFrame(parent, text=f"Saved in {DATA_DIR}/", padding=6)
        self.drawings_list = tk.Listbox(pane, height=12, exportselection=False)
        self.drawings_list.pack(fill=tk.BOTH, expand=True)
        self.drawings_list.bind("<Double-Button-1>", lambda _event: self._load_selected())

        buttons = ttk.Frame(pane)
        buttons.pack(fill=tk.X, pady=4)
        for text, command in (
            ("Load", self._load_selected),
            ("Delete", self._delete_selected),
            ("Refresh", self._populate_drawings_list),
        ):
            ttk.Button(buttons, text=text, width=DRAWING_BUTTON_WIDTH, command=command).pack(
                side=tk.LEFT, expand=True, fill=tk.X
            )
        return pane

    def _build_editor_pane(self, parent: ttk.PanedWindow) -> ttk.Frame:
        pane = ttk.Frame(parent)
        self.canvas = tk.Canvas(
            pane,
            width=EDITOR_PANE_MIN_WIDTH,
            bg=GRID_BACKGROUND,
            highlightthickness=1,
            highlightbackground=CANVAS_BORDER,
        )
        scrollbar = ttk.Scrollbar(pane, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=scrollbar.set)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))
        scrollbar.pack(fill=tk.X, padx=4)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)

        self.schedule_label = ttk.Label(pane, font=("TkDefaultFont", 9), justify=tk.LEFT)
        self.schedule_label.pack(anchor=tk.W, padx=4)
        return pane

    def _build_actions_pane(self, parent: ttk.PanedWindow) -> ttk.Frame:
        pane = ttk.Frame(parent)
        actions = ttk.LabelFrame(pane, text="Actions", padding=6)
        actions.pack(fill=tk.X, pady=(0, 6))
        actions.bind("<Configure>", self._wrap_hints)

        self.filename_var = tk.StringVar(value="my_art")
        ttk.Label(actions, text=f"Filename in {DATA_DIR}/ (no .txt):").pack(anchor=tk.W)
        filename_row = ttk.Frame(actions)
        filename_row.pack(fill=tk.X, pady=2)
        ttk.Entry(filename_row, textvariable=self.filename_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(filename_row, text="Save", command=self._save_drawing).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Separator(actions, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        self.target_repo_var = tk.StringVar()
        ttk.Label(actions, text="Target repository (GitHub URL or folder):").pack(anchor=tk.W)
        ttk.Entry(actions, textvariable=self.target_repo_var).pack(fill=tk.X, pady=2)
        self._add_hint(
            actions,
            "Any repo you own, e.g. your profile README repo. Deleting the repo removes the art.",
        )

        self.use_art_branch_var = tk.BooleanVar(value=False)
        self._art_branch_check = ttk.Checkbutton(
            actions,
            text="Advanced: use an art branch",
            variable=self.use_art_branch_var,
            command=self._toggle_art_branch,
        )
        self._art_branch_check.pack(anchor=tk.W, pady=(4, 0))
        self.art_branch_details = ttk.Frame(actions)
        branch_row = ttk.Frame(self.art_branch_details)
        branch_row.pack(fill=tk.X, pady=2)
        self.art_branch_var = tk.StringVar()
        ttk.Label(branch_row, text="Branch:").pack(side=tk.LEFT)
        ttk.Entry(branch_row, textvariable=self.art_branch_var, width=18).pack(side=tk.LEFT, padx=4)
        self._add_hint(
            self.art_branch_details, "Shows on your profile only once it is the default branch."
        )

        generate_row = ttk.Frame(actions)
        generate_row.pack(fill=tk.X, pady=2)
        self.generate_button = ttk.Button(
            generate_row, text="Generate Art", command=self._on_generate_clicked
        )
        self.generate_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.dry_run_button = ttk.Button(
            generate_row, text="Dry run", command=lambda: self._on_generate_clicked(dry_run=True)
        )
        self.dry_run_button.pack(side=tk.LEFT, padx=(4, 0))
        push_row = ttk.Frame(actions)
        push_row.pack(fill=tk.X, pady=2)
        self.push_button = ttk.Button(
            push_row, text="Push to GitHub", command=self._on_push_clicked, state=tk.DISABLED
        )
        self.push_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.force_var = tk.BooleanVar(value=False)
        self.force_button = ttk.Checkbutton(
            push_row, text="Force (dirty tree)", variable=self.force_var
        )
        self.force_button.pack(side=tk.LEFT, padx=(4, 0))

        log_frame = ttk.LabelFrame(pane, text="Log", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = ScrolledText(log_frame, height=LOG_LINES, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        return pane

    def _add_hint(self, parent: ttk.Frame | ttk.LabelFrame, text: str) -> None:
        hint = ttk.Label(
            parent,
            text=text,
            wraplength=ACTIONS_PANE_WIDTH - HINT_PADDING,
            foreground=HINT_COLOR,
        )
        hint.pack(anchor=tk.W, pady=(0, 4))
        self._hints.append(hint)

    def _toggle_art_branch(self) -> None:
        """Show the art branch field only while the advanced option is on."""
        if self.use_art_branch_var.get():
            self.art_branch_details.pack(fill=tk.X, after=self._art_branch_check)
        else:
            self.art_branch_details.pack_forget()

    def _wrap_hints(self, event: tk.Event) -> None:
        """Wrap the hints at the actions pane's current width."""
        for hint in self._hints:
            hint.configure(wraplength=max(1, event.width - HINT_PADDING))

    def _build_status_bar(self) -> None:
        self.status_var = tk.StringVar(value=STATUS_HINT)
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, padding=2).pack(
            fill=tk.X, side=tk.BOTTOM
        )

    def _fit_panes(self) -> None:
        """Keep every pane at least its minimum width; the grid pane scrolls instead.

        Runs whenever the paned window is resized or a sash is released. The first
        call with a real width places the sashes at the preferred pane widths;
        later calls keep the user's positions and only fix panes that became too
        narrow.
        """
        total = self._panes.winfo_width()
        if total <= 1:  # not mapped yet
            return
        if not self._panes_placed:
            self._panes_placed = True
            self._panes.sashpos(0, DRAWINGS_PANE_WIDTH)
            self._panes.sashpos(1, total - ACTIONS_PANE_WIDTH)
        actions_start = min(self._panes.sashpos(1), total - ACTIONS_PANE_MIN_WIDTH)
        drawings = min(self._panes.sashpos(0), actions_start - EDITOR_PANE_MIN_WIDTH)
        drawings = max(drawings, DRAWINGS_PANE_MIN_WIDTH)
        actions_start = max(actions_start, drawings + EDITOR_PANE_MIN_WIDTH)
        self._panes.sashpos(0, drawings)
        self._panes.sashpos(1, actions_start)
        self._panes.sashpos(0, drawings)

    # Grid editing ----------------------------------------------------------

    def _redraw(self) -> None:
        """Repaint every cell and refresh the schedule summary."""
        self.canvas.delete("all")
        for row in range(DAYS_PER_WEEK):
            for column in range(self.columns):
                x, y = column * CELL_SIZE, row * CELL_SIZE
                self.canvas.create_rectangle(
                    x,
                    y,
                    x + CELL_SIZE,
                    y + CELL_SIZE,
                    fill=level_color(self.grid[row][column]),
                    outline=CELL_OUTLINE,
                    tags=(f"cell_{row}_{column}",),
                )
        width, height = self.columns * CELL_SIZE, DAYS_PER_WEEK * CELL_SIZE
        self.canvas.config(height=height + 2, scrollregion=(0, 0, width, height))
        self._update_schedule_label()

    def _cell_at(self, event: tk.Event) -> tuple[int, int] | None:
        """Return the (row, column) under a mouse event, or None outside the grid."""
        row = int(self.canvas.canvasy(event.y)) // CELL_SIZE
        column = int(self.canvas.canvasx(event.x)) // CELL_SIZE
        if 0 <= row < DAYS_PER_WEEK and 0 <= column < self.columns:
            return row, column
        return None

    def _on_canvas_click(self, event: tk.Event) -> None:
        """Paint the selected level, or erase a cell that already has it.

        The result becomes the value the rest of the drag paints.
        """
        cell = self._cell_at(event)
        if cell is None:
            return
        level = self.level_var.get()
        self._stroke_value = 0 if self.grid[cell[0]][cell[1]] == level else level
        self._set_cell(*cell, self._stroke_value)

    def _on_canvas_drag(self, event: tk.Event) -> None:
        cell = self._cell_at(event)
        if cell is not None:
            self._set_cell(*cell, self._stroke_value)

    def _set_cell(self, row: int, column: int, level: int) -> None:
        if self.grid[row][column] != level:
            self.grid[row][column] = level
            self._redraw()

    def _resize_grid(self, columns: int) -> None:
        """Add empty columns or drop columns on the right, within the allowed width."""
        columns = max(MIN_COLUMNS, min(MAX_WEEKS, columns))
        if columns != self.columns:
            self.grid = [(row + [0] * columns)[:columns] for row in self.grid]
            self._redraw()

    def _clear_grid(self) -> None:
        self.grid = _empty_grid(self.columns)
        self._redraw()

    def _new_grid(self) -> None:
        self.grid = _empty_grid(DEFAULT_COLUMNS)
        self.filename_var.set("new_drawing")
        self._redraw()

    # Schedule (year / offset) ----------------------------------------------

    def _on_schedule_changed(self) -> None:
        self._update_schedule_label()
        self._suggest_art_branch()

    def _update_schedule_label(self) -> None:
        try:
            year, offset = self.year_var.get(), self.offset_var.get()
            start = get_first_sunday_of_year(year) + timedelta(weeks=offset)
        except tk.TclError, ValueError, OverflowError:
            self.schedule_label.config(text="Invalid year/offset")
            return
        end = start + timedelta(weeks=self.columns - 1, days=DAYS_PER_WEEK - 1)
        self.schedule_label.config(
            text=(
                f"Year {year}, offset {offset} weeks\n"
                f"{start.date()} (Sun) to {end.date()} (Sat), {count_commits(self.grid)} commits"
            )
        )

    def _suggest_art_branch(self) -> None:
        """Keep the art branch name at ``artworks-<year>`` unless the user typed their own."""
        try:
            year = self.year_var.get()
        except tk.TclError:  # the spinbox holds a non-number while typing
            return
        current = self.art_branch_var.get().strip()
        if (
            not current
            or current == ART_BRANCH_PREFIX
            or current.startswith(f"{ART_BRANCH_PREFIX}-")
        ):
            self.art_branch_var.set(f"{ART_BRANCH_PREFIX}-{year}")

    # Drawing files ---------------------------------------------------------

    def _populate_drawings_list(self) -> None:
        self.drawings_list.delete(0, tk.END)
        for path in sorted(DATA_DIR.glob("*.txt")):
            self.drawings_list.insert(tk.END, path.name)

    def _selected_drawing(self) -> str | None:
        selection = self.drawings_list.curselection()
        return self.drawings_list.get(selection[0]) if selection else None

    def _load_selected(self) -> None:
        name = self._selected_drawing()
        if name is None:
            return
        try:
            self.grid = load_grid(drawing_path(DATA_DIR, name))
        except (OSError, ValueError) as error:
            messagebox.showerror("Load error", str(error))
            return
        self.filename_var.set(Path(name).stem)
        self._redraw()
        self._log(f"Loaded {name}")

    def _delete_selected(self) -> None:
        name = self._selected_drawing()
        if name is None or not messagebox.askyesno("Delete", f"Delete {name}?"):
            return
        try:
            drawing_path(DATA_DIR, name).unlink(missing_ok=True)
        except (OSError, ValueError) as error:
            messagebox.showerror("Delete error", str(error))
        self._populate_drawings_list()

    def _save_drawing(self) -> None:
        try:
            path = drawing_path(DATA_DIR, self.filename_var.get())
            save_grid(path, self.grid)
        except (OSError, ValueError) as error:
            messagebox.showerror("Save error", str(error))
            return
        self._log(f"Saved to {path}")
        self._populate_drawings_list()

    # Generate and push -----------------------------------------------------

    def _prefill_target_repo(self) -> None:
        """Fill the target with the user's profile README repository, if detectable.

        Detection may query GitHub or run ``gh``, so it happens on a worker thread; a value the
        user typed in the meantime is kept. The worker only sees the result
        queue, so it never holds on to Tk objects.
        """
        results = self._detected_users

        def detect() -> None:
            if detected := detect_github_username():
                results.put(detected)

        threading.Thread(target=detect, daemon=True).start()

    def _set_default_target(self, username: str, source: str) -> None:
        if self.target_repo_var.get().strip():
            return
        self.target_repo_var.set(profile_repo_url(username))
        self._log(f"Target repository: your profile README repository (user from {source}).")

    def _on_generate_clicked(self, dry_run: bool = False) -> None:
        """Create the commits, or with ``dry_run`` only report how many are new."""
        target = self.target_repo_var.get().strip()
        if not target:
            messagebox.showerror(
                "Generate Art",
                "Enter the target repository first: a repository you own, e.g. your "
                "profile README repository https://github.com/<username>/<username>.",
            )
            return
        try:
            year, offset = self.year_var.get(), self.offset_var.get()
        except tk.TclError:
            messagebox.showerror("Generate Art", "Year and offset must be whole numbers.")
            return
        art_branch = self.art_branch_var.get().strip() if self.use_art_branch_var.get() else None
        where = f"branch '{art_branch}'" if art_branch else "the default branch"
        if not dry_run and not messagebox.askyesno(
            "Generate Art",
            f"This adds empty, backdated commits on {where} of:\n{target}\n\nContinue?",
        ):
            return
        force = self.force_var.get()
        grid = [row[:] for row in self.grid]

        self.generate_button.config(state=tk.DISABLED)
        self.dry_run_button.config(state=tk.DISABLED)
        self.push_button.config(state=tk.DISABLED)
        self.status_var.set("Checking..." if dry_run else "Generating...")

        kept: list[Path] = []

        def generate() -> None:
            try:
                apply_drawing(
                    grid=grid,
                    target_repo=target,
                    year=year,
                    offset_weeks=offset,
                    art_branch=art_branch,
                    force=force,
                    dry_run=dry_run,
                    on_clone_kept=kept.append,
                    log=self._queue_log,
                )
                temporary = is_remote_url(target)
                checkout = kept[0] if temporary and kept else None if temporary else Path(target)
                if not dry_run and checkout is not None:
                    branch = art_branch or _active_branch(git.Repo(checkout))
                    self._call_in_ui(lambda: self._set_push_target(checkout, branch, temporary))
            except Exception as error:  # report any failure in the log
                self._queue_log(f"Error: {error}")
            finally:
                self._call_in_ui(lambda: self.generate_button.config(state=tk.NORMAL))
                self._call_in_ui(lambda: self.dry_run_button.config(state=tk.NORMAL))
                self._call_in_ui(lambda: self.status_var.set(STATUS_READY))

        threading.Thread(target=generate, daemon=True).start()

    def _set_push_target(self, checkout: Path, branch: str | None, temporary: bool) -> None:
        """Enable Push for ``branch`` of ``checkout``; a temporary clone goes after the push."""
        self._push_target = (checkout, branch, temporary) if branch else None
        self.push_button.config(state=tk.NORMAL if branch else tk.DISABLED)

    def _on_push_clicked(self) -> None:
        if self._push_target is None:
            return
        checkout, branch, temporary = self._push_target
        self.push_button.config(state=tk.DISABLED)
        self.status_var.set("Pushing...")

        def push() -> None:
            pushed = False
            try:
                repo = git.Repo(checkout)
                try:
                    push_branch(repo, branch, self._queue_log)
                finally:
                    repo.close()
                pushed = True
                if temporary:
                    remove_tree(checkout.parent)
                    self._queue_log(f"Removed the temporary clone {checkout}.")
            except Exception as error:  # report any failure in the log
                self._queue_log(f"Error: push failed: {error}")
            finally:
                done = temporary and pushed
                self._call_in_ui(lambda: self._after_push(done))
                self._call_in_ui(lambda: self.status_var.set(STATUS_READY))

        threading.Thread(target=push, daemon=True).start()

    def _after_push(self, clone_removed: bool) -> None:
        """Re-enable Push, unless the temporary clone it pushed from is gone."""
        if clone_removed:
            self._push_target = None
        self.push_button.config(state=tk.DISABLED if clone_removed else tk.NORMAL)

    # Log and thread hand-off -----------------------------------------------

    def _queue_log(self, message: str) -> None:
        """Log from any thread."""
        self._log_queue.put(message)

    def _call_in_ui(self, func: Callable[[], object]) -> None:
        """Run ``func`` on the Tk main thread; safe to call from any thread."""
        self._ui_queue.put(func)

    def _drain_queues(self) -> None:
        for message in _drain(self._log_queue):
            self._log(message)
        for func in _drain(self._ui_queue):
            func()
        for username, source in _drain(self._detected_users):
            self._set_default_target(username, source)
        self.root.after(QUEUE_POLL_MS, self._drain_queues)

    def _log(self, message: str) -> None:
        """Append ``message`` to the log pane (main thread only)."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)


def _first_geometry(root: tk.Tk) -> str:
    """Return WINDOW_SIZE, shrunk to fit screens smaller than it."""
    width = min(WINDOW_SIZE[0], root.winfo_screenwidth() - WINDOW_SCREEN_MARGIN)
    height = min(WINDOW_SIZE[1], root.winfo_screenheight() - WINDOW_SCREEN_MARGIN)
    return f"{width}x{height}"


def _empty_grid(columns: int) -> Grid:
    return [[0] * columns for _ in range(DAYS_PER_WEEK)]


def _drain[T](items: queue.Queue[T]) -> list[T]:
    """Remove and return everything currently in ``items``."""
    drained: list[T] = []
    while True:
        try:
            drained.append(items.get_nowait())
        except queue.Empty:
            return drained


def _active_branch(repo: git.Repo) -> str | None:
    """Return the current branch name, or None when HEAD is detached."""
    return None if repo.head.is_detached else repo.active_branch.name


def main() -> None:
    """Entry point of the ``github-pixel-artworks-gui`` command."""
    root = tk.Tk()
    PixelArtGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
