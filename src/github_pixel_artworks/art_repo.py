"""The target repository: a repo the user owns, such as their profile README repo."""

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .config import TARGET_CLONE_DIR_NAME, TOOL_MARKER, URL_SCHEMES

type Log = Callable[[str], None]


def is_remote_url(target: str) -> bool:
    """Return True for a clone URL (``https://``, ``ssh://``, ``git@host:path``, ...)."""
    if target.startswith(URL_SCHEMES):
        return True
    user_host, colon, _path = target.partition(":")
    return bool(colon) and "@" in user_host and "/" not in user_host and "\\" not in user_host


def repo_folder_name(url: str) -> str:
    """Return the folder name ``git clone`` would use for ``url``."""
    return url.rstrip("/").removesuffix(".git").replace(":", "/").rsplit("/", 1)[-1]


def local_checkout_path(target: str, base_dir: Path | None = None) -> Path:
    """Return where the art repository lives on disk.

    A URL is cloned into ``base_dir`` (default: the working directory), in a folder
    named after the repository; a path is used as it is.
    """
    if not is_remote_url(target):
        return Path(target)
    return (base_dir or Path.cwd()) / repo_folder_name(target)


def tool_project_root() -> Path:
    """Return the project root this tool runs from, or the working directory.

    Walks up from this package looking for ``pyproject.toml`` and ``TOOL_MARKER``,
    so a URL target is always cloned into a fixed folder next to those files,
    regardless of the working directory. In an editable checkout that is the
    repository root. If the package is not running from a checkout (for example
    a site-packages install), the working directory is used instead.
    """
    return find_tool_project_root(Path(__file__).resolve()) or Path.cwd()


def find_tool_project_root(start: Path) -> Path | None:
    """Return the project root at or above ``start``, or None if there is none."""
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / TOOL_MARKER).is_file():
            return candidate
    return None


def target_clone_parent() -> Path:
    """Return the folder URL targets are cloned into (``target_cloned_repo``)."""
    return tool_project_root() / TARGET_CLONE_DIR_NAME


def clone_url_target(url: str, log: Log) -> git.Repo:
    """Clone ``url`` into ``target_cloned_repo/<repo>`` and return the clone.

    The parent folder sits at the tool's project root (see ``tool_project_root``).
    An existing folder at the same path is reused when it is a clone of ``url``:
    a clean clone is fetched and reset to the remote, so the run starts from
    what is on GitHub; a clone that still holds unpushed commits is left as it
    is. Anything else (a different remote, a non-git folder, uncommitted
    changes) raises ``RuntimeError`` and is not deleted. The caller removes the
    ``<repo>`` folder when done (and the parent if it is then empty).
    """
    parent = target_clone_parent()
    path = parent / repo_folder_name(url)
    if path.exists():
        return _open_existing_url_clone(url, path, log)
    parent.mkdir(parents=True, exist_ok=True)
    log(f"Cloning {url} into {path}...")
    try:
        return git.Repo.clone_from(url, path)
    except Exception:
        if path.exists():
            remove_tree(path)
        remove_dir_if_empty(parent)
        raise


def _open_existing_url_clone(url: str, path: Path, log: Log) -> git.Repo:
    """Reuse ``path`` when it is a safe clone of ``url``; otherwise raise."""
    try:
        repo = git.Repo(path)
    except InvalidGitRepositoryError, NoSuchPathError:
        repo = None
    if repo is None or "origin" not in repo.remotes or repo.remotes.origin.url != url:
        raise RuntimeError(
            f"{path} already exists and is not a clone of {url}. Move or delete it, then try again."
        )
    if repo.is_dirty(untracked_files=True):
        raise RuntimeError(
            f"{path} already exists and has uncommitted changes. "
            "Commit, move or delete them, then try again."
        )
    if _unpushed_or_unknown(repo):
        log(f"Using the existing clone at {path} (it holds unpushed commits).")
        return repo
    log(f"Updating the existing clone at {path}...")
    try:
        _refresh_clean_clone(repo)
    except GitCommandError as error:
        raise RuntimeError(
            f"Could not update the existing clone at {path}. Move or delete it, then try again."
        ) from error
    return repo


def _unpushed_or_unknown(repo: git.Repo) -> bool:
    try:
        return has_unpushed_commits(repo)
    except GitCommandError:
        return True  # when in doubt, do not reset


def _refresh_clean_clone(repo: git.Repo) -> None:
    """Fetch and reset a clean clone to the remote default branch."""
    repo.git.fetch("origin")
    branch = default_branch(repo)
    if branch is None:
        return
    repo.git.checkout(branch)
    repo.git.reset("--hard", f"origin/{branch}")


def has_unpushed_commits(repo: git.Repo) -> bool:
    """Return True if a local branch holds commits that no remote branch has."""
    return repo.git.rev_list("--count", "--branches", "--not", "--remotes") != "0"


def remove_tree(path: Path) -> None:
    """Delete ``path`` and everything in it, including read-only files.

    Git marks object files read-only, which makes a plain ``shutil.rmtree`` fail
    on Windows, so a failed delete is retried after making the item writable.
    """

    def make_writable_and_retry(func: Callable[[str], object], item: str, _error: object) -> None:
        for target in (os.path.dirname(item), item):
            if os.path.exists(target):
                os.chmod(target, stat.S_IRWXU)
        func(item)

    shutil.rmtree(path, onexc=make_writable_and_retry)


def remove_dir_if_empty(path: Path) -> None:
    """Remove ``path`` when it is an empty ``TARGET_CLONE_DIR_NAME`` folder."""
    if path.name != TARGET_CLONE_DIR_NAME:
        return
    try:
        path.rmdir()
    except OSError:
        pass


def open_art_repo(target: str, log: Log, base_dir: Path | None = None) -> git.Repo:
    """Open the art repository at ``target``, cloning it first when it is a URL.

    An earlier clone of the same URL is reused.

    Raises:
        RuntimeError: if a path is not a git repository, or the clone folder
            already holds something else.
    """
    path = local_checkout_path(target, base_dir)
    if not is_remote_url(target):
        return _open(path)
    if not path.exists():
        log(f"Cloning {target} into {path}...")
        return git.Repo.clone_from(target, path)
    try:
        repo = git.Repo(path)
    except InvalidGitRepositoryError, NoSuchPathError:
        repo = None
    if repo is None or "origin" not in repo.remotes or repo.remotes.origin.url != target:
        raise RuntimeError(
            f"{path} already exists and is not a clone of {target}. "
            "Move it away, or pass that folder as the target instead."
        )
    log(f"Using the existing clone at {path}.")
    return repo


def _open(path: Path) -> git.Repo:
    try:
        return git.Repo(path)
    except InvalidGitRepositoryError, NoSuchPathError:
        raise RuntimeError(f"{path} is not a git repository") from None


def default_branch(repo: git.Repo) -> str | None:
    """Return the default branch recorded by ``git clone`` (``origin/HEAD``), if any."""
    try:
        ref = repo.git.symbolic_ref("--quiet", "--short", "refs/remotes/origin/HEAD")
    except GitCommandError:
        return None
    return ref.removeprefix("origin/") or None


def is_tool_checkout(root: Path) -> bool:
    """Return True if ``root`` itself is a checkout of github-pixel-artworks.

    Only ``root`` is checked, not its parents, so a URL-target clone living in
    ``target_cloned_repo/<repo>`` inside this project is not treated as the
    tool: it is a separate git repository.
    """
    return (root / TOOL_MARKER).is_file()


def push_branch(repo: git.Repo, branch: str, log: Log) -> None:
    """Push ``branch`` to ``origin`` and track it.

    Raises:
        RuntimeError: if the repository has no ``origin`` remote.
    """
    if "origin" not in repo.remotes:
        raise RuntimeError(
            "The art repository has no 'origin' remote. Add one with: "
            "git remote add origin https://github.com/<you>/<repo>.git"
        )
    log(f"Pushing {branch} to origin...")
    repo.git.push("--set-upstream", "origin", branch)
    log("Push completed.")
