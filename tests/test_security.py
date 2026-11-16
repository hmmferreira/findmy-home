import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import patch
from findmy_home.storage import Store, atomic_json, read_json, token_only
from findmy_home.importer import normalized_plist
from findmy_home.auth import ExportFlow
from findmy_home.server import make_app

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_private_persistent_identity(self):
        first = Store(self.root)
        second = Store(self.root)
        self.assertEqual(first.identity, second.identity)
        self.assertEqual(stat.S_IMODE((self.root/"identity.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)
    def test_refuses_permissive_secret(self):
        Store(self.root)
        (self.root/"identity.json").chmod(0o644)
        with self.assertRaises(PermissionError):
            Store(self.root)
    def test_atomic_failure_preserves_old_state(self):
        path = self.root/"value.json"
        atomic_json(path, {"ok":1})
        with self.assertRaises(ValueError):
            atomic_json(path, {"bad":float("nan")})
        self.assertEqual(read_json(path), {"ok":1})
        self.assertFalse(list(self.root.glob(".*.tmp")))
    def test_password_never_serialized(self):
        class Account:
            def to_json(self):
                return {"account":{"username":"fixture","password":"DO_NOT_SAVE"},"login":{"state":4,"data":{"token":"fixture"}}}
        value = token_only(Account())
        self.assertIsNone(value["account"]["password"])
        self.assertNotIn("DO_NOT_SAVE", json.dumps(value))
    def test_selection_is_explicit_and_rejects_unknown(self):
        store = Store(self.root)
        store.items={"a":{"name":"A","enabled":False},"b":{"name":"B","enabled":True}}
        with self.assertRaises(ValueError):
            store.select(["missing"])
        self.assertTrue(store.items["b"]["enabled"])
        store.select(["a"])
        self.assertTrue(store.items["a"]["enabled"])
        self.assertFalse(store.items["b"]["enabled"])
    def test_public_snapshot_omits_secrets(self):
        store = Store(self.root)
        store.items={"a":{"name":"Item","enabled":True,"key_file":"PRIVATE_KEY_PATH"}}
        public = json.dumps(store.public())
        for secret in (store.identity["read_token"],store.identity["csrf_key"],"PRIVATE_KEY_PATH"):
            self.assertNotIn(secret, public)
    def test_fractional_export_dates_and_flat_key_fields(self):
        raw=plistlib.dumps({"pairingDate":datetime(2024,1,1),"privateKey":b"x"*28,"sharedSecret":b"s"*32})
        raw=raw.replace(b"2024-01-01T00:00:00Z",b"2024-01-01T00:00:00.125Z")
        result=normalized_plist(raw)
        self.assertEqual(result["pairingDate"],datetime(2024,1,1))
        self.assertEqual(result["privateKey"]["key"]["data"],b"x"*28)
    def test_rejects_xml_entity_expansion(self):
        with self.assertRaises(ValueError):
            normalized_plist(b'<!ENTITY attacker "x">')

class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name))
        self.clients=[]
    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        self.tmp.cleanup()
    async def client(self, management=False, peer="127.0.0.1"):
        client=TestClient(TestServer(make_app(self.store,management=management,trusted_peer=peer)))
        await client.start_server()
        self.clients.append(client)
        return client
    async def test_data_api_requires_token_and_is_read_only(self):
        client=await self.client()
        self.assertEqual((await client.get("/v1/snapshot")).status,401)
        auth={"Authorization":"Bearer "+self.store.identity["read_token"]}
        response=await client.get("/v1/snapshot",headers=auth)
        self.assertEqual(response.status,200)
        self.assertNotIn("csrf",await response.json())
        self.assertEqual((await client.post("/ui/login",headers=auth,json={"password":"fixture"})).status,404)
    async def test_forged_ingress_headers_from_other_peer_are_denied(self):
        client=await self.client(True,peer="172.30.32.2")
        response=await client.get("/v1/snapshot",headers={"X-Remote-User-Id":"admin","X-Forwarded-For":"172.30.32.2"})
        self.assertEqual(response.status,403)
    async def test_ingress_missing_user_is_denied(self):
        client=await self.client(True)
        self.assertEqual((await client.get("/v1/snapshot")).status,403)
    async def test_csrf_is_bound_to_ingress_user(self):
        client=await self.client(True)
        alice={"X-Remote-User-Id":"alice"}
        data=await (await client.get("/v1/snapshot",headers=alice)).json()
        self.assertEqual((await client.post("/ui/select",headers=alice,json={"ids":[]})).status,403)
        forged={"X-Remote-User-Id":"bob","X-CSRF-Token":data["csrf"]}
        self.assertEqual((await client.post("/ui/select",headers=forged,json={"ids":[]})).status,403)
        alice["X-CSRF-Token"]=data["csrf"]
        self.assertEqual((await client.post("/ui/select",headers=alice,json={"ids":[]})).status,200)
    async def test_recovery_requires_explicit_consent(self):
        client=await self.client(True)
        headers={"X-Remote-User-Id":"alice"}
        data=await (await client.get("/v1/snapshot",headers=headers)).json()
        headers["X-CSRF-Token"]=data["csrf"]
        self.assertEqual((await client.post("/ui/recovery",headers=headers,json={"action":"start"})).status,400)
    async def test_snapshot_disables_caching(self):
        client=await self.client()
        response=await client.get("/v1/snapshot",headers={"Authorization":"Bearer "+self.store.identity["read_token"]})
        self.assertEqual(response.headers["Cache-Control"],"no-store")

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.flow=ExportFlow(Path(self.tmp.name),str(Path(__file__).with_name("fake_exporter.py")))
    async def asyncTearDown(self):
        await self.flow.cancel(self.flow.owner)
        self.tmp.cleanup()
    async def test_prompt_journey_hides_raw_output_and_secrets(self):
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN":"synthetic-supervisor-token"}):
            await self.flow.start("alice")
        self.assertEqual(self.flow.state["kind"],"email")
        self.assertEqual(self.flow.visible("bob")["phase"],"busy")
        await self.flow.answer("alice","fixture@example.invalid")
        self.assertEqual(self.flow.state["kind"],"password")
        with self.assertRaises(ValueError):
            await self.flow.answer("bob","not-allowed")
        await self.flow.answer("alice","synthetic-password")
        self.assertEqual(self.flow.state["kind"],"verification_code")
        await self.flow.answer("alice","000000")
        self.assertEqual(self.flow.state["choices"],[{"value":0,"label":"Test iPhone"},{"value":1,"label":"Test Mac"}])
        self.assertNotIn("REDACTED_SERIAL",json.dumps(self.flow.state))
        with self.assertRaises(ValueError):
            await self.flow.answer("alice","99")
        await self.flow.answer("alice","1")
        self.assertEqual(self.flow.state["kind"],"device_passcode")
        await self.flow.answer("alice","123456")
        self.assertEqual(self.flow.state,{"phase":"complete"})
        for path in Path(self.tmp.name).rglob("*"):
            if path.is_file():
                self.assertNotIn("synthetic-password",path.read_text())
    async def test_control_characters_are_rejected_and_cancel_terminates_child(self):
        await self.flow.start("alice")
        with self.assertRaises(ValueError):
            await self.flow.answer("alice","first" + chr(10) + "second")
        child=self.flow.child
        await self.flow.cancel("alice")
        self.assertFalse(child.isalive())
        self.assertIsNone(self.flow.child)
