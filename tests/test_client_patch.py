import unittest

from tools.patch_client import endpoint_map, patch_methods


class PatchTests(unittest.TestCase):
    def test_rejects_untrusted_or_non_origin_inputs(self):
        for url in ("http://example.org", "https://user:password@example.org", "https://example.org/path", 'https://example.org/"', "https://example.org?x=y"):
            with self.assertRaises(ValueError):
                endpoint_map(url)

    def test_preserves_header_and_unrelated_overload(self):
        original = '.method static Z()Ljava/lang/String;\n .locals 4\n return-object v0\n.end method\n.method static Z(I)V\n return-void\n.end method'
        result, changes = patch_methods(original, {"Z": "https://api.example.org/v1/settings/application?applicationName=AndroidApp"})
        self.assertIn('.method static Z()Ljava/lang/String;\n    .locals 1', result)
        self.assertIn('.method static Z(I)V', result)
        self.assertEqual(len(changes), 1)

    def test_fails_closed_on_changed_client(self):
        with self.assertRaises(ValueError):
            patch_methods(".class public Ldifferent/client;", {"Z": "https://api.example.org"})


if __name__ == "__main__":
    unittest.main()
