import shutil
from pathlib import Path

import pytest

from attendflow.config import REPO_ROOT
from attendflow.data import Dataset, load_dataset

DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return load_dataset(DATA_DIR)


@pytest.fixture
def data_copy(tmp_path: Path) -> Path:
    """A throwaway copy of data/ that a test can break on purpose."""
    dst = tmp_path / "data"
    shutil.copytree(DATA_DIR, dst)
    return dst


def replace_in_file(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path.name}"
    path.write_text(text.replace(old, new, count), encoding="utf-8")
