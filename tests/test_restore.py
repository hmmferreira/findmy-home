"""Synthetic app-data restore and disk-failure tests, never real credentials."""
from datetime import datetime,timezone
import copy
import json
from pathlib import Path
import shutil
import plistlib
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from retrace.storage import Store,atomic_json,read_json
from retrace.worker import AppleWorker
from retrace.descriptions import enrich_metadata

class RestoreTests(unittest.TestCase):
    def test_complete_private_state_copy_preserves_identity_and_resets_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"original"
            original=Store(root)
            item="a"*32
            original.items={item:{"name":"Fixture","enabled":True,"key_file":item+".json"}}
            original.reports={item:{"latitude":1.,"longitude":2.,"accuracy":10.,"timestamp":"2024-01-01T00:00:00+00:00"}}
            values={"items.json":original.items,"reports.json":original.reports,
                "account.json":{"fixture_session":"PRIVATE_ACCOUNT_TOKEN"},
                "keys/"+item+".json":{"fixture_key":"PRIVATE_KEY"},
                "search/"+item+".json":{"version":1,"next_index":1234}}
            for name,value in values.items(): atomic_json(root/name,value)
            exporter=root/"export/state/exporter-session.plist"
            exporter.parent.mkdir(parents=True,mode=0o700)
            exporter.write_bytes(b"PRIVATE_EXPORTER_SESSION");exporter.chmod(0o600)
            original.health.update(status="ok",last_poll="2024-01-01T00:00:00+00:00")
            target=Path(tmp)/"restored"
            shutil.copytree(root,target,copy_function=shutil.copy2)
            restored=Store(target)
            self.assertEqual(original.identity,restored.identity)
            self.assertEqual(restored.items,original.items)
            self.assertEqual(restored.reports,original.reports)
            self.assertEqual(restored.health["status"],"starting")
            self.assertIsNone(restored.health["last_poll"])
            for name,value in values.items():
                self.assertEqual(read_json(target/name),value)
                self.assertEqual((target/name).stat().st_mode & 0o777,0o600)
            self.assertEqual((target/"export/state/exporter-session.plist").read_bytes(),b"PRIVATE_EXPORTER_SESSION")
            self.assertEqual(target.stat().st_mode & 0o777,0o700)
            self.assertNotIn("PRIVATE",json.dumps(restored.public()))

    def test_corrupt_identity_fails_instead_of_minting_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);Store(root)
            path=root/"identity.json";path.write_text("{corrupt")
            with self.assertRaises(ValueError): Store(root)
            self.assertEqual(path.read_text(),"{corrupt")

    def test_failed_selection_write_keeps_memory_and_disk_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp));store.items={"a":{"name":"Fixture","enabled":False}}
            atomic_json(store.root/"items.json",store.items)
            before=copy.deepcopy(store.items)
            with patch("retrace.storage.atomic_json",side_effect=OSError("synthetic disk full")):
                with self.assertRaises(OSError): store.select(["a"])
            self.assertEqual(store.items,before)
            self.assertEqual(read_json(store.root/"items.json"),before)

    def test_failed_sighting_write_does_not_publish_unsaved_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp));worker=AppleWorker(store)
            report={"latitude":1.,"longitude":2.,"accuracy":10.,"timestamp":datetime.now(timezone.utc).isoformat()}
            with patch("retrace.worker.atomic_json",side_effect=OSError("synthetic disk full")):
                with self.assertRaises(OSError): worker._accept_report("a",report)
            self.assertEqual(store.reports,{})
            self.assertFalse((store.root/"reports.json").exists())

    def test_failed_metadata_write_keeps_existing_descriptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp))
            store.items={"a":{"name":"Fixture","enabled":True,"key_file":"a.json"}}
            atomic_json(store.root/"keys/a.json",{"model":"iPhone17,2"})
            before=copy.deepcopy(store.items)
            with patch("retrace.descriptions.atomic_json",side_effect=OSError("synthetic disk full")):
                with self.assertRaises(OSError): enrich_metadata(store)
            self.assertEqual(store.items,before)

    def test_failed_inventory_write_does_not_publish_imported_items(self):
        from retrace.importer import import_exports
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/"data")
            source=Path(tmp)/"exports";source.mkdir()
            (source/"fixture.plist").write_bytes(plistlib.dumps({"identifier":"fixture-id","model":"iPhone17,2"}))
            def write(path,value):
                if path.name=="items.json": raise OSError("synthetic disk full")
                atomic_json(path,value)
            accessory=SimpleNamespace(to_json=lambda:{"fixture":"PRIVATE_KEY"})
            with patch("findmy.FindMyAccessory.from_plist",return_value=accessory), patch("retrace.importer.atomic_json",side_effect=write):
                with self.assertRaises(OSError): import_exports(store,source)
            self.assertEqual(store.items,{})
            self.assertFalse((store.root/"items.json").exists())
