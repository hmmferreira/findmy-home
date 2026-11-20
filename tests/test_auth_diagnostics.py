"""Synthetic factor refusal/retry and stage logs without credentials or SDK prose."""
import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
import logging
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

from findmy import LoginState,errors as sdk_errors
from findmy.reports.twofactor import AsyncSmsSecondFactor,AsyncTrustedDeviceSecondFactor
from findmy_home.apple_transport import VerificationFailure,TransportBlocked
from findmy_home.worker import AppleWorker,AuthenticationError,_auth_classification
from findmy_home.shared_ui import SharedDiscoveryUI
from findmy_home.storage import Store

class AuthDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name))
        self.account=SimpleNamespace(login_state=LoginState.REQUIRE_2FA,_password="PRIVATE_PASSWORD",
            close=AsyncMock(),login=AsyncMock(return_value=LoginState.REQUIRE_2FA),
            sms_2fa_request=AsyncMock(),sms_2fa_submit=AsyncMock(),td_2fa_request=AsyncMock(),td_2fa_submit=AsyncMock())
        self.methods=[AsyncSmsSecondFactor(self.account,7,"PRIVATE_PHONE_NUMBER"),AsyncTrustedDeviceSecondFactor(self.account)]
        self.account.get_2fa_methods=AsyncMock(return_value=self.methods)
        self.writer=AsyncMock()
        self.worker=AppleWorker(self.store,account_factory=AsyncMock(return_value=self.account),session_writer=self.writer)
        self.output=StringIO();self.capture=redirect_stdout(self.output);self.capture.__enter__()
        self.bridge=None
    async def asyncTearDown(self):
        if self.bridge is not None:await self.bridge.close()
        await self.worker.cancel("owner");await self.worker.close()
        self.capture.__exit__(None,None,None);self.tmp.cleanup()
    async def login(self):return await self.worker.login("owner","PRIVATE_EMAIL","PRIVATE_PASSWORD")
    def events(self):
        lines=self.output.getvalue().splitlines()
        self.assertTrue(all(line.startswith("Find My Home auth: ") for line in lines))
        self.assertTrue(all(len(line)<512 for line in lines))
        self.assertNotIn("PRIVATE",self.output.getvalue())
        return [json.loads(line.removeprefix("Find My Home auth: ")) for line in lines]
    async def success(self,*args):
        self.account.login_state=LoginState.LOGGED_IN
        return LoginState.LOGGED_IN
    async def test_sms_request_logs_only_stage_kind_and_safe_labels(self):
        self.assertEqual(await self.login(),{"phase":"choose_method","methods":[{"value":0,"label":"SMS"},{"value":1,"label":"Trusted device"}]})
        self.assertEqual(await self.worker.factor("owner",0),{"phase":"verification_code","method":0})
        self.account.sms_2fa_request.assert_awaited_once_with(7)
        self.assertEqual(self.events()[-1],{"stage":"2fa_request","event":"completed","method":"sms"})
    async def test_typed_submit_refusal_keeps_challenge_until_explicit_retry(self):
        await self.login();await self.worker.factor("owner",0)
        self.account.sms_2fa_submit.side_effect=VerificationFailure("submit",400)
        result=await self.worker.factor("owner",0,"123456")
        self.assertEqual(result,{"phase":"verification_code","method":0,"error":"verification_not_accepted"})
        self.assertIs(self.worker.pending,self.account);self.account.close.assert_not_awaited()
        self.writer.assert_not_awaited();self.account.sms_2fa_submit.assert_awaited_once_with(7,"123456")
        await asyncio.sleep(0)
        self.assertEqual(self.account.sms_2fa_submit.await_count,1)
        self.account.sms_2fa_submit.side_effect=self.success
        self.assertEqual(await self.worker.factor("owner",0,"654321"),{"phase":"complete"})
        self.assertEqual(self.account.sms_2fa_submit.await_count,2)
        self.writer.assert_awaited_once_with(self.account)
        self.assertIsNone(self.worker.pending);self.assertIsNone(self.account._password)
        self.assertIn({"stage":"2fa_submit","event":"failed","method":"sms","error":"verification_not_accepted","kind":"verification_refused","status":400},self.events())
    async def test_request_rejection_keeps_method_choice_without_automatic_resend(self):
        await self.login();self.account.sms_2fa_request.side_effect=VerificationFailure("request",403)
        result=await self.worker.factor("owner",0)
        self.assertEqual(result["phase"],"choose_method");self.assertEqual(result["error"],"code_request_failed")
        self.account.sms_2fa_request.assert_awaited_once_with(7)
        self.assertIs(self.worker.pending,self.account);self.account.close.assert_not_awaited()
        self.assertEqual(self.events()[-1]["status"],403)
    async def test_rate_limit_is_explicit_not_mislabelled_invalid_code(self):
        await self.login();self.account.sms_2fa_submit.side_effect=VerificationFailure("submit",429)
        self.assertEqual(await self.worker.factor("owner",0,"123456"),
            {"phase":"verification_code","method":0,"error":"verification_rate_limited"})
        self.account.sms_2fa_submit.assert_awaited_once_with(7,"123456")
        self.assertEqual(self.events()[-1]["status"],429)
    async def test_ambiguous_sdk_submit_failure_closes_account_and_never_matches_prose(self):
        await self.login();self.account.sms_2fa_submit.side_effect=sdk_errors.UnhandledProtocolError("invalid code PRIVATE_PHONE_NUMBER PRIVATE_TOKEN")
        with self.assertRaises(AuthenticationError) as caught:await self.worker.factor("owner",0,"123456")
        self.assertEqual(caught.exception.code,"verification_rejected")
        self.assertIsNone(self.worker.pending);self.account.close.assert_awaited_once()
        self.assertIsNone(self.account._password);self.events()
    async def test_unknown_network_submit_outcome_does_not_replay_or_keep_password(self):
        await self.login();self.account.sms_2fa_submit.side_effect=TimeoutError("PRIVATE_HTTP_URL")
        with self.assertRaises(AuthenticationError) as caught:await self.worker.factor("owner",0,"123456")
        self.assertEqual(caught.exception.code,"authentication_network_error")
        self.assertIsNone(self.worker.pending);self.account.sms_2fa_submit.assert_awaited_once()
        self.assertIsNone(self.account._password);self.events()
    async def test_network_request_failure_can_be_explicitly_requested_again(self):
        await self.login();self.account.sms_2fa_request.side_effect=TransportBlocked("request_failed")
        result=await self.worker.factor("owner",0)
        self.assertEqual(result["error"],"authentication_network_error");self.assertEqual(result["phase"],"choose_method")
        self.assertIs(self.worker.pending,self.account)
        self.account.sms_2fa_request.side_effect=None
        self.assertEqual(await self.worker.factor("owner",0),{"phase":"verification_code","method":0})
        self.assertEqual(self.account.sms_2fa_request.await_count,2);self.events()
    async def test_post_verification_save_error_is_distinct_from_rejected_code(self):
        await self.login();self.account.sms_2fa_submit.side_effect=self.success
        self.writer.side_effect=OSError("PRIVATE_SESSION_PATH")
        with self.assertRaises(AuthenticationError) as caught:await self.worker.factor("owner",0,"123456")
        self.assertEqual(caught.exception.code,"session_save_failed")
        self.assertEqual(caught.exception.stage,"session_save")
        self.assertEqual(self.events()[-1],{"stage":"session_save","event":"failed","method":"sms","error":"session_save_failed","kind":"storage"})
        self.assertIsNone(self.account._password)
    async def test_discovery_handoff_failure_has_own_stage_after_saved_account(self):
        self.account.login.return_value=LoginState.LOGGED_IN
        self.worker.authenticated=AsyncMock(side_effect=RuntimeError("PRIVATE_PET"))
        with self.assertRaises(AuthenticationError) as caught:await self.login()
        self.assertEqual(caught.exception.code,"discovery_handoff_failed")
        self.writer.assert_awaited_once()
        self.assertEqual(self.events()[-1],{"stage":"discovery_handoff","event":"failed","error":"discovery_handoff_failed","kind":"handoff"})
        self.assertIsNone(self.account._password)
    async def test_shared_ui_preserves_retry_phase_method_and_error(self):
        self.bridge=SharedDiscoveryUI(AsyncMock());self.bridge.bind(self.worker)
        await self.bridge.authenticate("owner",lambda:self.login());await self.bridge.auth_task
        self.account.sms_2fa_submit.side_effect=VerificationFailure("submit",401)
        await self.bridge.authenticate("owner",lambda:self.worker.factor("owner",0,"123456"));await self.bridge.auth_task
        self.assertEqual(self.bridge.auth_visible("owner"),{"phase":"verification_code","method":0,"error":"verification_not_accepted"})
        self.assertEqual(self.bridge.auth_visible("another-user"),{"phase":"busy"})
        self.events()
    async def test_known_refusal_after_state_advanced_does_not_keep_challenge(self):
        await self.login();self.account.login_state=LoginState.AUTHENTICATED
        self.account.sms_2fa_submit.side_effect=VerificationFailure("submit",400)
        with self.assertRaises(AuthenticationError):await self.worker.factor("owner",0,"123456")
        self.assertIsNone(self.worker.pending);self.account.close.assert_awaited_once();self.events()
    async def test_global_sdk_logging_stays_disabled_and_structured_events_still_emit(self):
        previous=logging.root.manager.disable
        try:
            logging.disable(logging.CRITICAL)
            await self.login();await self.worker.factor("owner",1)
            self.assertEqual(logging.root.manager.disable,logging.CRITICAL)
        finally:logging.disable(previous)
        self.assertEqual(self.events()[-1]["method"],"trusted_device")
    def test_only_explicit_sdk_invalid_code_type_is_recoverable(self):
        class TypedInvalidCode(Exception):pass
        with patch.object(sdk_errors,"InvalidCodeError",TypedInvalidCode,create=True):
            self.assertEqual(_auth_classification(TypedInvalidCode("PRIVATE_CODE"),"2fa_submit"),
                ("invalid_verification_code",True,"verification_code_rejected"))
        class InvalidCodeError(Exception):pass
        self.assertEqual(_auth_classification(InvalidCodeError("PRIVATE_CODE"),"2fa_submit"),
            ("verification_rejected",False,"unclassified"))
    def test_event_whitelist_drops_injected_values(self):
        self.worker._auth_event("2fa_submit","failed",method="PRIVATE_PHONE",error="PRIVATE_CODE",kind="PRIVATE_TOKEN",status=123456,reason={"PRIVATE":"VALUE"})
        self.assertEqual(self.events(),[{"stage":"2fa_submit","event":"failed"}])
