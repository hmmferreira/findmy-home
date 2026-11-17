import os
from pathlib import Path
import tempfile
import unittest
from findmy_home.private_data import prepare_private_root
from findmy_home.storage import Store,atomic_json

class PrivateDataTests(unittest.TestCase):
    def test_restored_modes_are_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"data";path=root/"nested/state.json"
            path.parent.mkdir(parents=True);path.write_text("synthetic");path.chmod(0o644)
            prepare_private_root(root)
            self.assertEqual(root.stat().st_mode & 0o777,0o700)
            self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_root_symlink_rejected_without_changing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"target";target.mkdir();target.chmod(0o755)
            root=Path(tmp)/"data";root.symlink_to(target,target_is_directory=True)
            with self.assertRaises(ValueError): prepare_private_root(root)
            with self.assertRaises(PermissionError): Store(root)
            self.assertEqual(target.stat().st_mode & 0o777,0o755)

    def test_symlink_directory_file_fifo_and_hardlink_fail_before_permissions_change(self):
        for kind in ("directory","file","fifo","hardlink"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/"data";root.mkdir();root.chmod(0o755)
                outside=Path(tmp)/"outside";outside.write_text("synthetic");outside.chmod(0o644)
                path=root/"unexpected"
                if kind=="directory": path.symlink_to(Path(tmp),target_is_directory=True)
                elif kind=="file": path.symlink_to(outside)
                elif kind=="fifo": os.mkfifo(path)
                else: os.link(outside,path)
                with self.assertRaises(ValueError): prepare_private_root(root)
                self.assertEqual(root.stat().st_mode & 0o777,0o755)
                self.assertEqual(outside.stat().st_mode & 0o777,0o644)

    def test_incomplete_restore_does_not_create_replacement_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);atomic_json(root/"items.json",{})
            with self.assertRaises(ValueError): Store(root)
            self.assertFalse((root/"identity.json").exists())

    def test_well_formed_but_invalid_identity_is_not_used_or_replaced(self):
        for value in ({},[],{"instance_id":"invalid"}):
            with self.subTest(value=value),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);atomic_json(root/"identity.json",value)
                before=(root/"identity.json").read_bytes()
                with self.assertRaises(ValueError): Store(root)
                self.assertEqual((root/"identity.json").read_bytes(),before)
