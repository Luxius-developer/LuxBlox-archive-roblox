"""Apply the R9 attribution change to an already-R8 decoded Android client."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from tools.patch_native_bundle import DMP, chunks, read_string, rbx_string, unpack_script, pack_script
from tools.patch_native_r8 import patch_script, scripts
from tools.luau_v1 import parse


def patch(decoded, compiler):
    root = Path(decoded)
    obb = root / "assets/main.1.com.roblox.client.obb"
    temp = obb.with_suffix(".r9.tmp")
    report = []
    with zipfile.ZipFile(obb) as src, zipfile.ZipFile(temp, "w") as dst:
        model = src.read(DMP)
        classes, counts, names = scripts(model)
        out = model[:32]
        for kind, payload, reserved in classes:
            if kind == b"PROP":
                class_id = int.from_bytes(payload[:4], "little")
                prop, pos = read_string(payload, 4)
                value_type = payload[pos]
                pos += 1
                if prop == b"Source" and value_type == 29:
                    updated = payload[:pos]
                    for index in range(counts[class_id]):
                        blob, pos = read_string(payload, pos)
                        name = names[class_id][index]
                        if blob and re.fullmatch(r"[a-z]{2}(?:-[a-z]+)?", name):
                            raw = unpack_script(blob)
                            if b"CommonUI.Features.Label.FMODCredits" in parse(raw)["strings"]:
                                replacement, changes = patch_script(raw, index, name, compiler)
                                if changes:
                                    blob = pack_script(replacement)
                                    report.append({"module": name, "index": index,
                                                   "sha256": hashlib.sha256(replacement).hexdigest()})
                        updated += rbx_string(blob)
                    payload = updated
            out += __import__("struct").pack("<4sIII", kind, 0, len(payload), reserved) + payload
        if not report:
            raise ValueError("No localized FMOD attribution module found in the decoded R8 OBB")
        for info in src.infolist():
            dst.writestr(info, out if info.filename == DMP else src.read(info))
    temp.replace(obb)
    return {"modules": report, "native_libraries_modified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded")
    parser.add_argument("--compiler", required=True)
    args = parser.parse_args()
    print(json.dumps(patch(args.decoded, args.compiler), ensure_ascii=False, indent=2))
