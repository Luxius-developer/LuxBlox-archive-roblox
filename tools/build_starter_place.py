#!/usr/bin/env python3
"""Generate an original, script-free miniature obby in Roblox XML v4."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent


def property_(parent, tag, name, value):
    node = ET.SubElement(parent, tag, name=name)
    node.text = str(value)
    return node


def item(parent, class_name, name, referent):
    node = ET.SubElement(parent, "Item", {"class": class_name, "referent": referent})
    props = ET.SubElement(node, "Properties")
    property_(props, "string", "Name", name)
    return node, props


def part(parent, name, position, size, rgb, spawn=False):
    node, props = item(parent, "SpawnLocation" if spawn else "Part", name, "RBX_" + name)
    property_(props, "bool", "Anchored", "true")
    property_(props, "bool", "CanCollide", "true")
    property_(props, "token", "TopSurface", 0)
    property_(props, "token", "BottomSurface", 0)
    property_(props, "token", "Material", 256)
    property_(props, "Color3uint8", "Color3uint8", (255 << 24) | (rgb[0] << 16) | (rgb[1] << 8) | rgb[2])
    vector = ET.SubElement(props, "Vector3", name="size")
    for axis, value in zip("XYZ", size):
        ET.SubElement(vector, axis).text = str(value)
    frame = ET.SubElement(props, "CoordinateFrame", name="CFrame")
    for axis, value in zip("XYZ", position):
        ET.SubElement(frame, axis).text = str(value)
    for row in range(3):
        for col in range(3):
            ET.SubElement(frame, f"R{row}{col}").text = str(int(row == col))
    if spawn:
        property_(props, "bool", "Neutral", "true")
        property_(props, "bool", "Enabled", "true")
        property_(props, "int", "Duration", 0)
    return node


def build():
    root = ET.Element("roblox", version="4")
    ET.SubElement(root, "External").text = "null"
    ET.SubElement(root, "External").text = "nil"
    workspace, props = item(root, "Workspace", "Workspace", "RBX_Workspace")
    property_(props, "float", "FallenPartsDestroyHeight", -60)
    part(workspace, "StartPlatform", (0, 6, 0), (20, 1, 20), (49, 64, 88))
    part(workspace, "StartSpawn", (0, 7, 0), (8, 1, 8), (255, 177, 57), spawn=True)
    for index in range(10):
        part(workspace, f"Jump{index + 1:02}", (-3 if index % 2 == 0 else 3, 6 + index * 0.5, 17 + index * 11),
             (8, 1, 8), (70, 177, 221) if index % 2 == 0 else (255, 177, 57))
    part(workspace, "FinishPlatform", (0, 11, 134), (20, 1, 20), (64, 202, 125))
    item(root, "Players", "Players", "RBX_Players")
    _, lighting = item(root, "Lighting", "Lighting", "RBX_Lighting")
    property_(lighting, "float", "ClockTime", 14)
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


if __name__ == "__main__":
    path = ROOT / "places/LuxBlox-Starter-Obby.rbxlx"
    path.parent.mkdir(parents=True, exist_ok=True)
    build().write(path, encoding="utf-8", xml_declaration=False)
    print(path)
