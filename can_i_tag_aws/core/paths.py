"""Filesystem locations for reports and caches.

Resolved relative to the project root so they stay stable regardless of which
module runs or where it lives inside the package. The project root is the parent
of the ``can_i_tag_aws`` package directory (this file is at
``can_i_tag_aws/core/paths.py``, so the root is three levels up).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "output"
HISTORY_DIR = PROJECT_ROOT / "history"
CACHE_DIR = PROJECT_ROOT / ".cache"
