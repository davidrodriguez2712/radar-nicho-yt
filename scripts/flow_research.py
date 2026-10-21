# scripts/flow_research.py
"""Thin wrapper so the skill can run ``uv run python scripts/flow_research.py <command>``."""

import sys

from nicheradar.flow_research.cli import main

if __name__ == "__main__":
    sys.exit(main())
