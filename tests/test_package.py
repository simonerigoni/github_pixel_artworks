"""The public API exported by the package."""

import github_pixel_artworks


def test_every_name_in_all_is_importable() -> None:
    for name in github_pixel_artworks.__all__:
        assert hasattr(github_pixel_artworks, name), name


def test_version_is_set() -> None:
    assert github_pixel_artworks.__version__
