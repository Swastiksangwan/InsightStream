#!/usr/bin/env python3
"""Backward-friendly focused entry point for the shared videos refresh scope."""

from __future__ import annotations

import sys

from analytics.scripts.refresh.run_content_refresh import main


if __name__ == "__main__":
    if "--scope" in sys.argv[1:]:
        print("refresh_content_videos.py is fixed to the videos scope; omit --scope.")
        sys.exit(2)
    sys.exit(main(["--scope", "videos", *sys.argv[1:]]))
