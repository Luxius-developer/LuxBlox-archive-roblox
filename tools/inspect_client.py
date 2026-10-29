#!/usr/bin/env python3
"""Read-only inventory of an APK or an apktool directory. Standard library only.

Does not modify APKs, signatures, DEX checksums or native libraries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile


def dex_strings(data):
    if len(data) < 112 or not data.startswith(b"dex\n"):
        raise ValueError("Expected a normal, uncompressed DEX file")
    count, offset = struct.unpack_from("<II", data, 56)
    if offset + count * 4 > len(data):
        raise ValueError("Invalid DEX string table")
    for index in range(count):
        pos = struct.unpack_from("<I", data, offset + index * 4)[0]
        # Skip the ULEB128 UTF-16 character count; relevant literals are ASCII.
        for _ in range(5):
            if pos >= len(data):
                raise ValueError("Invalid DEX string offset")
            value = data[pos]
            pos += 1
            if value < 128:
                break
        else:
            raise ValueError("Invalid DEX string length")
        end = data.find(b"\0", pos)
        if end < 0:
            raise ValueError("Unterminated DEX string")
        yield data[pos:end].decode("utf-8", errors="replace")


def inspect(path):
    archive = zipfile.ZipFile(path) if path.is_file() else None
    try:
        names = archive.namelist() if archive else [str(p.relative_to(path)) for p in path.rglob("*") if p.is_file()]
        selected = sorted(n for n in names if n.endswith(".dex") or (n.startswith("lib/") and n.endswith(".so")))
        results = []
        for name in selected:
            data = archive.read(name) if archive else (path / name).read_bytes()
            entry = {"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if name.endswith(".dex"):
                values = list(dex_strings(data))
                entry["relevant_literals"] = sorted(v for v in values if (
                    "pekora.zip" in v or v in {
                        "applicationSettings", "v1/settings/application?applicationName=",
                        "v2/settings/application/", "v1/login", "v2/login", "v2/signup",
                        "device/initialize", "mobileapi/check-app-version?appVersion=",
                        "v1/mobile-client-version?appVersion=",
                        "FFlagEnableRandomRobloxChannelSelection",
                    }))
            else:
                entry["legacy_hosts"] = sorted(set(x.decode("ascii") for x in re.findall(
                    rb"(?:[A-Za-z0-9_-]+\.)*(?:pekora\.zip|roblox\.com)", data)))
            results.append(entry)
        return {"abis": sorted({n.split("/")[1] for n in selected if n.startswith("lib/")}), "files": results}
    finally:
        if archive:
            archive.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.client), ensure_ascii=False, indent=2))
