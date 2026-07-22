"""Stable repository paths for analytics commands."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
ANALYTICS_ROOT = REPO_ROOT / "analytics"
ANALYTICS_CONFIG_DIR = ANALYTICS_ROOT / "config"
ANALYTICS_PROCESSED_DIR = ANALYTICS_ROOT / "processed"
ANALYTICS_RAW_DIR = ANALYTICS_ROOT / "raw"
BACKEND_ROOT = REPO_ROOT / "backend"

if not (REPO_ROOT / "analytics" / "scripts").is_dir():  # pragma: no cover
    raise RuntimeError(f"Unable to resolve InsightStream repository root from {__file__}")


def ensure_backend_import_path() -> None:
    """Expose the backend's top-level ``app`` package to analytics audits."""
    backend_path = str(BACKEND_ROOT)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
