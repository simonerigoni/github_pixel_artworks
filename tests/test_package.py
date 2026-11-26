"""The public API exported by the package, including constants at their old import paths."""

import importlib

import pytest

import github_pixel_artworks
from github_pixel_artworks import config


def test_every_name_in_all_is_importable() -> None:
    for name in github_pixel_artworks.__all__:
        assert hasattr(github_pixel_artworks, name), name


def test_version_is_set() -> None:
    assert github_pixel_artworks.__version__


@pytest.mark.parametrize(
    ("module", "name"),
    [
        ("artwork", "MAX_WEEKS"),
        ("artwork", "LEVEL_COLORS"),
        ("dates", "MAX_YEAR"),
        ("dates", "COMMIT_HOUR_UTC"),
        ("github", "FETCH_TIMEOUT_SECONDS"),
        ("painter", "ART_MESSAGE_PREFIX"),
        ("cli", "EXIT_BAD_ARGUMENT"),
        ("gui", "CELL_SIZE"),
    ],
)
def test_constants_are_still_importable_from_their_old_modules(module: str, name: str) -> None:
    old_home = importlib.import_module(f"github_pixel_artworks.{module}")

    assert getattr(old_home, name) is getattr(config, name)
