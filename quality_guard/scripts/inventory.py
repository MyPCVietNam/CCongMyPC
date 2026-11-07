#!/usr/bin/env python3
"""Offline source file inventory. Avoids reading any contents/secrets."""
from collections import Counter
from pathlib import Path
import argparse, json
p = argparse.ArgumentParser(); p.add_argument('root', type=Path); args = p.parse_args()
root = args.root
files = [x for x in root.rglob('*') if x.is_file() and not any(
    part in {'.git','node_modules','.venv','__pycache__'} for part in x.parts)]
counts = Counter(x.suffix.lower() or '[none]' for x in files)
print(json.dumps({'files': len(files), 'by_suffix': dict(counts),
                  'test_files': sum(x.name.startswith('test_') and x.suffix=='.py' for x in files),
                  'powershell_files': counts.get('.ps1', 0)}, indent=2))
