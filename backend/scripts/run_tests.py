#!/usr/bin/env python3
"""Run pytest with private, explicit test configuration, or without PostgreSQL."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_ENV = Path.home() / "Library" / "Application Support" / "InsightStream" / "test.env"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-only", action="store_true")
    parser.add_argument("--test-env", type=Path, default=PRIVATE_ENV)
    parser.add_argument("--migration-env", type=Path)
    parser.add_argument("--migration-fixtures", action="store_true")
    parser.add_argument("--migration-only", action="store_true")
    args, pytest_args = parser.parse_known_args()
    if args.migration_env:
        # A separate outside-repository path can otherwise influence pytest's
        # early root discovery before nested conftest options are registered.
        pytest_args.insert(0, "--migration-env=" + str(args.migration_env.expanduser()))
    if args.migration_fixtures:
        pytest_args.insert(0, "--migration-fixtures")
    if args.migration_only:
        pytest_args.insert(0, "--migration-only")
    # Nested conftest options are discovered from an explicit test path. With
    # only flags, pytest may treat an as-yet-unknown custom option as a filename.
    selected_path = False
    for value in pytest_args:
        if value.startswith("-"):
            continue
        candidate = (REPO_ROOT / value.split("::", 1)[0]).resolve()
        if candidate.exists() and (candidate == REPO_ROOT or REPO_ROOT in candidate.parents):
            selected_path = True
            break
    if not selected_path:
        pytest_args.insert(0, str(REPO_ROOT / "backend/tests"))
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("TMDB_READ_ACCESS_TOKEN", None)
    if args.unit_only:
        environment.pop("TEST_DATABASE_URL", None)
        pytest_args.insert(0, "--unit-only")
    else:
        if args.test_env.exists():
            if args.test_env.stat().st_mode & 0o077:
                parser.error("The test environment file must have mode 0600.")
            values = {key: value for key, value in dotenv_values(args.test_env).items() if value is not None}
            for key in ("TEST_DATABASE_URL", "INSIGHTSTREAM_ENV"):
                if key not in environment and key in values:
                    environment[key] = values[key]
    return subprocess.call([sys.executable, "-m", "pytest", "-c", str(REPO_ROOT / "pytest.ini"), *pytest_args], cwd=REPO_ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
