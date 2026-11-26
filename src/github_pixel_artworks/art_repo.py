"""The target repository: a repo the user owns, such as their profile README repo."""

import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from .config import CLONE_TEMP_PREFIX, TOOL_MARKER, URL_SCHEMES

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


def clone_to_temp(url: str, log: Log) -> git.Repo:
    """Clone ``url`` into a new temporary folder and return the clone.

    The folder is made by ``tempfile.mkdtemp`` with ``CLONE_TEMP_PREFIX``, so it is
    never inside the tool's checkout and every run starts from what is on GitHub.
    The caller removes it (``remove_tree`` on the clone's parent) when done.
    """
    folder = Path(tempfile.mkdtemp(prefix=CLONE_TEMP_PREFIX))
    path = folder / repo_folder_name(url)
    log(f"Cloning {url} into the temporary folder {path}...")
    try:
        return git.Repo.clone_from(url, path)
    except Exception:
        remove_tree(folder)
        raise


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
    """Return True if ``root`` is a checkout of github-pixel-artworks itself."""
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
