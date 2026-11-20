from datetime import datetime
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch
from findmy_home.storage import Store,atomic_json,read_json
from findmy_home.descriptions import metadata,enrich_metadata

class DescriptionTests(unittest.TestCase):
    def test_model_date_and_original_name_without_hardware_identifiers(self):
        value=metadata({"name":"iPhone","model":"iPhone17,2","pairingDate":datetime(2024,1,2),
                        "serialNumber":"PRIVATE_SERIAL","identifier":"PRIVATE_IDENTIFIER","privateKey":"PRIVATE_KEY"})
        self.assertEqual(value["model_name"],"iPhone 16 Pro Max")
        self.assertEqual(value["paired_at"],"2024-01-02")
        self.assertEqual(value["apple_name"],"iPhone")
        self.assertNotIn("PRIVATE",json.dumps(value))

    def test_unknown_model_and_missing_date_are_not_guessed(self):
        value=metadata({"model":"FuturePhone99,1","paired_at":"not a date"})
        self.assertEqual(value["model_name"],"FuturePhone99,1")
        self.assertIsNone(value["paired_at"])
        self.assertIsNone(metadata({})["model_name"])

    def test_upgrade_backfills_without_rediscovery_or_key_rewrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp))
            store.items={"a"*32:{"name":"iPhone","enabled":True,"key_file":"fixture.json"}}
            key=store.root/"keys/fixture.json"
            atomic_json(key,{"model":"iPhone17,2","paired_at":"2024-02-03T00:00:00+00:00",
                             "master_key":"PRIVATE_KEY","serial_number":"PRIVATE_SERIAL"})
            before=key.read_bytes()
            enrich_metadata(store)
            item=store.public()["items"][0]
            self.assertEqual(item["model_name"],"iPhone 16 Pro Max")
            self.assertEqual(item["paired_at"],"2024-02-03")
            self.assertEqual(key.read_bytes(),before)
            self.assertTrue(store.items["a"*32]["enabled"])
            self.assertNotIn("PRIVATE",json.dumps(store.public()))
            self.assertEqual(read_json(store.root/"items.json")["a"*32]["paired_at"],"2024-02-03")

    def test_original_export_name_is_available_without_rewriting_existing_name(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp))
            identifier="fixture-device"
            item_id=hashlib.sha256(identifier.encode()).hexdigest()[:32]
            store.items={item_id:{"name":"iPhone old display","enabled":True,"key_file":"absent.json"}}
            source=store.root/"export/accessories/fixture.plist"
            source.parent.mkdir(parents=True)
            source.write_bytes(plistlib.dumps({"identifier":identifier,"name":"Owner’s iPhone",
                                               "model":"iPhone18,2","pairingDate":datetime(2025,1,1)}))
            enrich_metadata(store)
            self.assertEqual(store.items[item_id]["name"],"iPhone old display")
            self.assertEqual(store.items[item_id]["apple_name"],"Owner’s iPhone")
            self.assertEqual(store.items[item_id]["model_name"],"iPhone 17 Pro Max")

    def test_legacy_channel_is_edge_and_stable_stays_stable(self):
        path=Path(__file__).resolve().parents[1]/"custom_components/findmy_home/const.py"
        spec=importlib.util.spec_from_file_location("findmy_constants",path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.normalize_channel("beta"),"edge")
        self.assertEqual(module.normalize_channel(None),"edge")
        self.assertEqual(module.entry_title("edge"),"Retrace Edge")
        self.assertEqual(module.entry_title("stable"),"Retrace")

    def test_retrace_default_title_migration_preserves_custom_titles_and_domain(self):
        path=Path(__file__).resolve().parents[1]/"custom_components/findmy_home/const.py"
        spec=importlib.util.spec_from_file_location("retrace_constants",path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.DOMAIN,"findmy_home")
        for title in ("Find My Home", "Find My Home Edge", "Find My Home (Beta)"):
            self.assertEqual(module.migrated_entry_title(title,"edge"),"Retrace Edge")
            self.assertEqual(module.migrated_entry_title(title,"stable"),"Retrace")
        self.assertEqual(module.migrated_entry_title("My personal tracker","edge"),"My personal tracker")
