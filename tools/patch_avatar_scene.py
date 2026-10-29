#!/usr/bin/env python3
"""Replace the mismatched Mobile place using a hash-pinned client resource."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ENTRY = 'ExtraContent/places/Mobile.rbxl'


def patch(obb, reference, expected_old, expected_new):
    obb = Path(obb)
    with zipfile.ZipFile(reference) as src:
        replacement = src.read(ENTRY)
    if hashlib.sha256(replacement).hexdigest() != expected_new:
        raise ValueError('Reference Mobile place hash mismatch')
    temporary = obb.with_suffix('.scene.tmp')
    with zipfile.ZipFile(obb) as src, zipfile.ZipFile(temporary, 'w') as dst:
        if hashlib.sha256(src.read(ENTRY)).hexdigest() != expected_old:
            raise ValueError('Unexpected existing Mobile place; refusing blind replacement')
        for info in src.infolist():
            dst.writestr(info, replacement if info.filename == ENTRY else src.read(info))
    temporary.replace(obb)
    return {'entry': ENTRY, 'before': expected_old, 'after': expected_new}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('obb', type=Path)
    p.add_argument('reference', type=Path)
    p.add_argument('--old-sha256', required=True)
    p.add_argument('--new-sha256', required=True)
    a = p.parse_args()
    print(json.dumps(patch(a.obb, a.reference, a.old_sha256, a.new_sha256), indent=2))
