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
    args, pytest_args = parser.parse_known_args()
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
    return subprocess.call([sys.executable, "-m", "pytest", *pytest_args], cwd=REPO_ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
