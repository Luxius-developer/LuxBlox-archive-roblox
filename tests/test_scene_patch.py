import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
from tools.patch_avatar_scene import patch, ENTRY


class ScenePatchTests(unittest.TestCase):
    def test_only_pinned_scene_changes_and_wrong_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            obb, reference = root/'client.obb', root/'reference.obb'
            with zipfile.ZipFile(obb, 'w') as z:
                z.writestr(ENTRY, b'old scene')
                z.writestr('protected-script', b'unchanged')
            with zipfile.ZipFile(reference, 'w') as z:
                z.writestr(ENTRY, b'new scene')
            before = obb.read_bytes()
            old = hashlib.sha256(b'old scene').hexdigest()
            new = hashlib.sha256(b'new scene').hexdigest()
            with self.assertRaises(ValueError):
                patch(obb, reference, old, '0'*64)
            self.assertEqual(obb.read_bytes(), before)
            patch(obb, reference, old, new)
            with zipfile.ZipFile(obb) as z:
                self.assertEqual(z.read(ENTRY), b'new scene')
                self.assertEqual(z.read('protected-script'), b'unchanged')
            with self.assertRaises(ValueError):
                patch(obb, reference, old, new)
