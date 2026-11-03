#!/usr/bin/env python3
"""Read-only ZIP entry-name audit; never reads or prints file content.

Usage: python Verify-Archive-NoSecrets.py <source.zip>
Exit 0 safe, exit 2 denied paths, exit 1 usage/invalid.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Reuse the fail-closed scanner (supports nested ZIPs).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sensitive_path_scanner import main as scanner_main


if __name__ == "__main__":
    raise SystemExit(scanner_main())
