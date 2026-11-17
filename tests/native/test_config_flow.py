"""Run with the supported Home Assistant Core, isolated from app dependencies."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from homeassistant.data_entry_flow import AbortFlow

ROOT=Path(__file__).resolve().parents[2]
package=ModuleType("custom_components.findmy_home")
package.__path__=[str(ROOT/"custom_components/findmy_home")]
sys.modules[package.__name__]=package
spec=importlib.util.spec_from_file_location(package.__name__+".config_flow",Path(package.__path__[0])/"config_flow.py")
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def setup_flow(self):
        flow=module.FindMyHomeFlow()
        flow.hass=SimpleNamespace()
        info=SimpleNamespace(slug="fixture_findmy_home",config={"host":"fixture-findmy-home","token":"n"*64,"instance_id":"a"*32,"channel":"edge","unrelated":"DO_NOT_RETAIN"})
        existing=SimpleNamespace(unique_id="a"*32)
        return flow,info,existing

    async def test_verified_same_instance_rediscovery_updates_existing_connection(self):
        flow,info,existing=self.setup_flow()
        api=SimpleNamespace(snapshot=AsyncMock(return_value={"instance_id":"a"*32,"channel":"edge"}))
        with patch.object(flow,"async_set_unique_id",AsyncMock(return_value=existing)), patch.object(flow,"_abort_if_unique_id_configured",side_effect=AbortFlow("already_configured")) as update, patch.object(module,"Api",return_value=api), patch.object(module,"async_get_clientsession"):
            with self.assertRaises(AbortFlow): await flow.async_step_hassio(info)
        api.snapshot.assert_awaited_once()
        data=update.call_args.kwargs["updates"]
        self.assertEqual(data["token"],"n"*64)
        self.assertEqual(data["instance_id"],existing.unique_id)
        self.assertNotIn("unrelated",data)

    async def test_wrong_identity_never_replaces_existing_credentials(self):
        flow,info,existing=self.setup_flow()
        api=SimpleNamespace(snapshot=AsyncMock(return_value={"instance_id":"b"*32,"channel":"edge"}))
        with patch.object(flow,"async_set_unique_id",AsyncMock(return_value=existing)), patch.object(flow,"_abort_if_unique_id_configured") as update, patch.object(module,"Api",return_value=api), patch.object(module,"async_get_clientsession"):
            result=await flow.async_step_hassio(info)
        self.assertEqual(result["reason"],"wrong_instance")
        update.assert_not_called()

    async def test_failed_verification_preserves_existing_credentials(self):
        flow,info,existing=self.setup_flow()
        api=SimpleNamespace(snapshot=AsyncMock(side_effect=module.Unauthorized()))
        with patch.object(flow,"async_set_unique_id",AsyncMock(return_value=existing)), patch.object(flow,"_abort_if_unique_id_configured") as update, patch.object(module,"Api",return_value=api), patch.object(module,"async_get_clientsession"):
            result=await flow.async_step_hassio(info)
        self.assertEqual(result["reason"],"cannot_connect")
        update.assert_not_called()

    async def test_invalid_discovery_host_is_rejected_before_network_access(self):
        flow,info,existing=self.setup_flow();info.config["host"]="attacker.example"
        with patch.object(module,"Api") as api:
            result=await flow.async_step_hassio(info)
        self.assertEqual(result["reason"],"cannot_connect")
        api.assert_not_called()
