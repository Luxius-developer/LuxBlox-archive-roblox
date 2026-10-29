#!/usr/bin/env python3
"""Patch reviewed Java URL generators in the decoded 2021 test client.

This is a bootstrap test build, not an all-endpoint/native-game-porting tool.
Run on a fresh Apktool decode of the verified source APK.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ANDROID = "{http://schemas.android.com/apk/res/android}"
PACKAGE = "com.luxius.luxblox"
ORIGINAL_PACKAGE = "com.roblox.clienc"


def endpoint_map(origin):
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or not re.fullmatch(r"[a-zA-Z0-9.-]+(?::[0-9]+)?", parsed.netloc)):
        raise ValueError("api-base must be an HTTPS origin without credentials, query or path")
    base = origin.rstrip("/") + "/"
    host = parsed.netloc
    return {
        "a": host + "/", "b": host + "/", "c": host, "d": base, "f": host,
        "n": base, "o": base, "p": base, "q": base, "G": base, "ac": base,
        "aa": base,
        "Y": base + "realtime/notifications",
        "Z": base + "v1/settings/application?applicationName=AndroidApp",
        "aj": base + "mobile/pbe",
        "al": base + "v1.1/Counters/Increment/?client=LuxBlox",
        "am": base + "v1.0/SequenceStatistics/AddToSequence?client=LuxBlox",
        "an": base + "v1/performance/send-measurement",
    }


def patch_methods(source, routes):
    changes = []
    for name, value in routes.items():
        pattern = re.compile(r"(^\.method [^\n]*\b" + re.escape(name)
                             + r"\(\)Ljava/lang/String;\n).*?^\.end method", re.M | re.S)
        matches = list(pattern.finditer(source))
        if len(matches) != 1 or "static" not in matches[0].group(1):
            raise ValueError(f"Expected exactly one static {name}() string method")
        header = matches[0].group(1)
        replacement = header + '    .locals 1\n\n    const-string v0, "' + value + '"\n\n    return-object v0\n.end method'
        source = pattern.sub(lambda _: replacement, source, count=1)
        changes.append({"method": name + "()Ljava/lang/String;", "url": value})
    return source, changes


def patch(decoded, origin):
    routes = endpoint_map(origin)
    paths = list(decoded.glob("smali*/com/roblox/client/u.smali"))
    if len(paths) != 1:
        raise ValueError("Expected one reviewed 2021 URL generator class")
    path = paths[0]
    source, changes = patch_methods(path.read_text(), routes)
    source = source.replace('"www.pekora.zip/"', '"' + urlsplit(origin).netloc + '/"')
    source = source.replace("https://en.help.pekora.zip/hc/en-us/articles/212459863", origin.rstrip("/") + "/help")
    manifest = decoded / "AndroidManifest.xml"
    tree = ET.parse(manifest)
    root = tree.getroot()
    if root.attrib.get("package") != ORIGINAL_PACKAGE:
        raise ValueError("Expected original com.roblox.clienc manifest; decode afresh")
    root.set("package", PACKAGE)
    app = root.find("application")
    if app is None:
        raise ValueError("Missing Android application declaration")
    app.set(ANDROID + "label", "LuxBlox")
    # Keep Java class names as com.roblox.client. Only the distinct application
    # ID and its matching authority/permission constants are changed.
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if ORIGINAL_PACKAGE in value:
                element.set(key, value.replace(ORIGINAL_PACKAGE, PACKAGE))
    ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
    path.write_text(source)
    tree.write(manifest, encoding="utf-8", xml_declaration=True)
    for pattern in ("smali*/**/*.smali", "res/**/*.xml"):
        for item in decoded.glob(pattern):
            text = item.read_text()
            if ORIGINAL_PACKAGE in text:
                item.write_text(text.replace(ORIGINAL_PACKAGE, PACKAGE))
    return {"package": PACKAGE, "profile": "java-bootstrap-only", "patched_methods": changes,
            "native_libraries_modified": False, "tls_verification_disabled": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decoded", type=Path)
    parser.add_argument("--api-base", required=True)
    args = parser.parse_args()
    print(json.dumps(patch(args.decoded, args.api_base), ensure_ascii=False, indent=2))

