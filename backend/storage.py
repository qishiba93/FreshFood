"""Shared paths for bundled assets and runtime uploads."""
import os
import shutil
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_STATIC_DIR = BACKEND_DIR / "static"
PERSISTENT_DATA_DIR = os.getenv("PERSISTENT_DATA_DIR", "").strip()

if PERSISTENT_DATA_DIR:
    STATIC_DATA_DIR = Path(PERSISTENT_DATA_DIR).expanduser().resolve()
else:
    STATIC_DATA_DIR = PROJECT_STATIC_DIR

UPLOAD_DIR = STATIC_DATA_DIR / "uploads"
COMMUNITY_DIR = UPLOAD_DIR / "community"
DEFAULTS_DIR = UPLOAD_DIR / "defaults"
STANDARDS_DIR = STATIC_DATA_DIR / "standards"


def _copy_seed_files(source: Path, target: Path) -> None:
    if not source.exists() or source.resolve() == target.resolve():
        return
    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue
        relative_path = source_file.relative_to(source)
        target_file = target / relative_path
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)


for directory in (UPLOAD_DIR, COMMUNITY_DIR, DEFAULTS_DIR, STANDARDS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

if PERSISTENT_DATA_DIR:
    _copy_seed_files(PROJECT_STATIC_DIR / "standards", STANDARDS_DIR)
    _copy_seed_files(PROJECT_STATIC_DIR / "uploads" / "defaults", DEFAULTS_DIR)
