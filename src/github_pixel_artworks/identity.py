"""The git identity (``user.name`` and ``user.email``) the art commits are made with."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import GIT_CONFIG_TIMEOUT_SECONDS, IDENTITY_FIX_HINT

IDENTITY_KEYS = {"name": "user.name", "email": "user.email"}


@dataclass(frozen=True)
class Identity:
    """Who the art commits are authored and committed by."""

    name: str
    email: str

    def env(self) -> dict[str, str]:
        """Return the git environment that makes this the author and the committer."""
        return {
            f"GIT_{role}_{field.upper()}": getattr(self, field)
            for role in ("AUTHOR", "COMMITTER")
            for field in IDENTITY_KEYS
        }

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class MissingIdentityError(RuntimeError):
    """Raised when neither the target nor the current folder has a git identity."""

    def __init__(self) -> None:
        super().__init__(
            "No git identity: user.name and user.email are not both set in the target "
            "repository or where the tool runs, so the commits cannot be made. " + IDENTITY_FIX_HINT
        )


def git_config(key: str, cwd: Path | None = None, *, local: bool = False) -> str | None:
    """Return the git setting ``key`` in effect in ``cwd`` (default: the working directory).

    That is the repository's, then the global, then the system value; with
    ``local`` only the repository's own. Returns None if it is unset or git fails.
    """
    scope = ["--local"] if local else []
    try:
        result = subprocess.run(
            ["git", "config", *scope, "--get", key],
            capture_output=True,
            text=True,
            timeout=GIT_CONFIG_TIMEOUT_SECONDS,
            check=False,
            cwd=cwd,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def resolve_identity(target: Path | None = None) -> Identity | None:
    """Return the identity for commits in the ``target`` repository, or None if incomplete.

    Each field comes from the first place that sets it: the ``GIT_AUTHOR_*``
    environment, the target's own (local) config, then the settings in effect in
    the working directory (its repository, global, system), the same ones the
    GitHub username detection reads. So a target cloned next to the tool still
    gets the identity of the checkout the tool runs from.
    """
    values: dict[str, str] = {}
    for field, key in IDENTITY_KEYS.items():
        value = os.environ.get(f"GIT_AUTHOR_{field.upper()}")
        if not value and target is not None:
            value = git_config(key, target, local=True)
        value = value or git_config(key)
        if not value:
            return None
        values[field] = value
    return Identity(**values)
