import tempfile
import unittest
from pathlib import Path
from organizer import organize, undo


class OrganizerTests(unittest.TestCase):
    def test_preview_apply_collision_and_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'photo.JPG').write_bytes(b'image')
            (root / 'note.txt').write_text('new', encoding='utf-8')
            (root / 'LICENSE').write_text('license', encoding='utf-8')
            (root / 'nested').mkdir()
            (root / 'nested' / 'keep.txt').write_text('keep')
            (root / 'ext_txt').mkdir()
            (root / 'ext_txt' / 'note.txt').write_text('old')
            before = sorted(str(p.relative_to(root)) for p in root.rglob('*'))
            self.assertIsNone(organize(root))
            self.assertEqual(before, sorted(str(p.relative_to(root)) for p in root.rglob('*')))
            log = organize(root, True)
            self.assertEqual((root / 'ext_txt' / 'note (1).txt').read_text(), 'new')
            self.assertEqual((root / 'ext_txt' / 'note.txt').read_text(), 'old')
            self.assertTrue((root / 'ext_jpg' / 'photo.JPG').exists())
            self.assertTrue((root / 'no_extension' / 'LICENSE').exists())
            self.assertTrue((root / 'nested' / 'keep.txt').exists())
            self.assertEqual(undo(log), 3)
            self.assertFalse((root / 'note.txt').exists())
            self.assertEqual(undo(log, True), 3)
            self.assertEqual((root / 'note.txt').read_text(), 'new')
            self.assertEqual((root / 'photo.JPG').read_bytes(), b'image')
            self.assertEqual(undo(log, True), 0)

    def test_undo_preserves_new_or_modified_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'a.txt').write_text('original')
            (root / 'b.txt').write_text('original')
            log = organize(root, True)
            (root / 'a.txt').write_text('new file')
            (root / 'ext_txt' / 'b.txt').write_text('edited')
            self.assertEqual(undo(log, True), 0)
            self.assertEqual((root / 'a.txt').read_text(), 'new file')
            self.assertEqual((root / 'ext_txt' / 'b.txt').read_text(), 'edited')


if __name__ == '__main__':
    unittest.main()
