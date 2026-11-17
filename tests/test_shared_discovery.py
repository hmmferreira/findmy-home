"""Synthetic coverage for the experimental single-account discovery controller."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from findmy_home.shared_discovery import SharedDiscovery,SharedDiscoveryError,TokenLease,python_client

class SharedDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.record=SimpleNamespace(device_name="iPhone",device_model="Test model",serial="PRIVATE_SERIAL",metadata={"secret":"PRIVATE"})
        self.client=SimpleNamespace(recovery_options=AsyncMock(return_value=SimpleNamespace(recoverable=[self.record])),
            unlock=AsyncMock(),accessories=AsyncMock(return_value=[object()]),close=AsyncMock())
        self.account=SimpleNamespace(login_state=SimpleNamespace(name="LOGGED_IN"),_password="PRIVATE_PASSWORD",close=AsyncMock())
        self.factory=AsyncMock(return_value=self.client)
        self.commit=AsyncMock()
        self.flow=SharedDiscovery(self.commit,factory=self.factory)
    async def asyncTearDown(self):
        await self.flow.cancel(self.flow.owner)
    async def ready(self):
        await self.flow.start("owner",self.account)
        await self.flow.task
        return self.flow.visible("owner")
    async def test_one_existing_account_no_exporter_or_second_credential_prompt(self):
        result=await self.ready()
        self.factory.assert_awaited_once_with(self.account)
        self.assertIsNone(self.account._password)
        self.assertEqual(result["kind"],"device_unlock")
        self.assertNotIn("PRIVATE",json.dumps(result))
        self.assertEqual(self.flow.visible("someone-else"),{"phase":"busy"})
        choice=result["choices"][0]["value"]
        await self.flow.unlock("owner",choice,"synthetic-passcode")
        await self.flow.task
        self.client.unlock.assert_awaited_once_with(self.record,"synthetic-passcode")
        self.commit.assert_awaited_once()
        self.assertEqual(self.flow.visible("owner"),{"phase":"complete","item_count":1})
        self.account.close.assert_not_awaited()
        self.client.close.assert_awaited_once()
    async def test_wrong_owner_or_unknown_choice_never_attempts_passcode(self):
        result=await self.ready();choice=result["choices"][0]["value"]
        for owner,value in (("other",choice),("owner","invented")):
            with self.assertRaises(SharedDiscoveryError): await self.flow.unlock(owner,value,"fixture")
        self.client.unlock.assert_not_awaited()
    async def test_inputs_reject_control_characters(self):
        result=await self.ready()
        for value in ("", "bad\ninput", "bad\x00input", "x"*513):
            with self.assertRaises(SharedDiscoveryError): await self.flow.unlock("owner",result["choices"][0]["value"],value)
        self.client.unlock.assert_not_awaited()
    async def test_failure_is_redacted_and_never_retries_a_passcode(self):
        result=await self.ready()
        self.client.unlock.side_effect=RuntimeError("PRIVATE_UPSTREAM_BODY")
        await self.flow.unlock("owner",result["choices"][0]["value"],"PRIVATE_PASSCODE")
        await self.flow.task
        self.assertEqual(self.flow.visible("owner"),{"phase":"failed","error":"discovery_failed"})
        self.client.unlock.assert_awaited_once()
        self.commit.assert_not_awaited()
    async def test_empty_recovery_list_is_not_successful_discovery(self):
        self.client.recovery_options.return_value=SimpleNamespace(recoverable=[])
        result=await self.ready()
        self.assertEqual(result["error"],"no_recovery_devices")
        self.commit.assert_not_awaited()
    async def test_start_returns_immediately_and_cancel_reaps_pending_work(self):
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def blocked(account):
            entered.set()
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        self.flow.factory=blocked
        result=await self.flow.start("owner",self.account)
        self.assertEqual(result["phase"],"working")
        await asyncio.wait_for(entered.wait(),1)
        await self.flow.cancel("owner")
        self.assertTrue(cancelled.is_set())
        self.assertIsNone(self.account._password)
        self.assertIsNone(self.flow.task)
        self.assertEqual(self.flow.visible("owner"),{"phase":"cancelled"})
    async def test_timeout_and_expiry_close_client(self):
        self.flow.timeout=.01
        self.client.recovery_options.side_effect=lambda:None
        async def blocked(): await asyncio.Event().wait()
        self.client.recovery_options.side_effect=blocked
        result=await self.ready()
        self.assertEqual(result["error"],"timed_out")
        self.client.close.assert_awaited_once()
    async def test_unauthenticated_account_cannot_start(self):
        self.account.login_state.name="REQUIRE_2FA"
        with self.assertRaises(SharedDiscoveryError): await self.flow.start("owner",self.account)
        self.factory.assert_not_awaited()
    async def test_simultaneous_start_does_not_replace_the_owner(self):
        await self.ready()
        with self.assertRaises(SharedDiscoveryError): await self.flow.start("other",self.account)
        self.assertEqual(self.flow.owner,"owner")
    async def test_service_token_is_memory_only_expiring_and_revocable(self):
        clock=[0]
        lease=TokenLease(self.account,"PRIVATE_TOKEN",clock=lambda:clock[0],lifetime=10)
        self.assertEqual(await lease.request_pet(),"PRIVATE_TOKEN")
        clock[0]=10
        with self.assertRaises(SharedDiscoveryError): await lease.request_pet()
        lease.release();self.assertIsNone(lease._token)
    async def test_backend_receives_password_free_lease_and_cannot_reauthenticate(self):
        self.account.request_pet=AsyncMock(return_value="PRIVATE_TOKEN")
        opened=[]
        async def open_client(lease):
            self.assertIsNone(self.account._password)
            self.assertEqual(await lease.request_pet(),"PRIVATE_TOKEN")
            opened.append(lease)
            return self.client
        module=SimpleNamespace(AsyncFindMyClient=SimpleNamespace(open=open_client))
        with patch.dict("sys.modules",{"findmy.icloud":module}):
            client=await python_client(self.account)
        self.account.request_pet.assert_awaited_once()
        self.assertFalse(hasattr(client,"join"));self.assertFalse(hasattr(client,"rename"));self.assertFalse(hasattr(client,"session"))
        await client.close()
        with self.assertRaises(SharedDiscoveryError): await opened[0].request_pet()

    async def test_flow_lifetime_expires_without_retaining_client(self):
        self.flow.lifetime=.01
        await self.ready()
        await asyncio.sleep(.03)
        self.assertEqual(self.flow.visible("owner"),{"phase":"expired"})
        self.assertIsNone(self.flow.client)
        self.assertEqual(self.flow.records,{})
    async def test_commit_failure_is_not_reported_as_success(self):
        result=await self.ready()
        self.commit.side_effect=OSError("PRIVATE_DISK_FAILURE")
        await self.flow.unlock("owner",result["choices"][0]["value"],"fixture")
        await self.flow.task
        self.assertEqual(self.flow.visible("owner"),{"phase":"failed","error":"discovery_failed"})

    async def test_immediate_cancel_before_worker_starts_clears_transient_password(self):
        await self.flow.start("owner",self.account)
        await self.flow.cancel("owner")
        self.factory.assert_not_awaited()
        self.assertIsNone(self.account._password)
        self.assertIsNone(self.flow._pending_account)
