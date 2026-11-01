#!/usr/bin/env python3
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integration.targets import from_marker

if __name__ == '__main__':
    marker = json.loads((Path(sys.argv[1]) / 'BEYOUD-WORKSPACE.json').read_text())
    print(from_marker(marker)[0])
