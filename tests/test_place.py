import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from tools.build_starter_place import build

ROOT = Path(__file__).parents[1]


class PlaceTests(unittest.TestCase):
    def test_stored_place_matches_generator_and_has_safe_static_geometry(self):
        root = ET.parse(ROOT / "places/LuxBlox-Starter-Obby.rbxlx").getroot()
        self.assertEqual(ET.tostring(root), ET.tostring(build().getroot()))
        refs = [x.attrib["referent"] for x in root.iter("Item")]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertEqual(root.attrib["version"], "4")
        self.assertFalse(any(x.attrib["class"] in ("Script", "LocalScript", "ModuleScript") for x in root.iter("Item")))
        spawn = root.findall('.//Item[@class="SpawnLocation"]')
        self.assertEqual(len(spawn), 1)
        parts = [x for x in root.iter("Item") if x.attrib["class"] in ("Part", "SpawnLocation")]
        self.assertEqual(len(parts), 13)
        for part in parts:
            self.assertEqual(part.find('Properties/bool[@name="Anchored"]').text, "true")
            self.assertTrue(all(float(n.text) > 0 for n in part.find('Properties/Vector3[@name="size"]')))

    def test_catalog_does_not_invent_players_votes_or_running_server(self):
        catalog = json.loads((ROOT / "places/catalog.json").read_text())
        game = catalog["experiences"][0]
        self.assertTrue((ROOT / game["placeFile"]).is_file())
        self.assertFalse(game["isPlayable"])
        self.assertEqual(game["playing"], 0)
        self.assertEqual(game["upVotes"], 0)
        self.assertEqual(game["downVotes"], 0)
        self.assertIsNone(game["ratingPercent"])


if __name__ == "__main__":
    unittest.main()
