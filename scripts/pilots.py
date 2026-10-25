# scripts/pilots.py
"""Acciones del humano sobre los pilotos: ``uv run python scripts/pilots.py ...``."""

import sys

from nicheradar.pilots.cli import main

if __name__ == "__main__":
    sys.exit(main())
