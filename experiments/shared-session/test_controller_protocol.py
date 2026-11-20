"""Our controller over real candidate crypto and synthetic account fixtures."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fake_account import Accessory,a_whole_account
from findmy.icloud import AsyncFindMyClient
from findmy_home.apple_transport import OwnedHttpSession
from findmy_home.shared_discovery import SharedDiscovery

@pytest.mark.asyncio
async def test_controller_delivers_decrypted_accessories_without_rust_or_second_login(monkeypatch):
    whole=a_whole_account([Accessory(name="Keys",identifier="SYNTHETIC-BEACON")])
    whole.use_the_view(monkeypatch)
    session=whole.circle.session()
    session.recovery_options=AsyncMock(return_value=SimpleNamespace(recoverable=[whole.circle.peer.record]))
    session.recover=AsyncMock(return_value=whole.circle.peer)
    session.close=AsyncMock()
    account=SimpleNamespace(_http=OwnedHttpSession(),login_state=SimpleNamespace(name="LOGGED_IN"),_password="synthetic-transient-password",
                            request_pet=AsyncMock(return_value="synthetic-service-token"))
    async def open_client(lease):
        assert account._password is None
        assert await lease.request_pet()=="synthetic-service-token"
        client=AsyncFindMyClient(lease,session,whole.data.store())
        unlock=client.unlock
        async def fixture_view(record,passcode):
            return await unlock(record,passcode,views=("Manatee",))
        client.unlock=fixture_view
        return client
    monkeypatch.setattr("findmy_home.owned_protocol.open_shared_client",open_client)
    saved=[]
    async def commit(accessories): saved.extend(accessories)
    flow=SharedDiscovery(commit)
    try:
        await flow.start("owner",account);await flow.task
        state=flow.visible("owner")
        assert state["phase"]=="input"
        await flow.unlock("owner",state["choices"][0]["value"],"synthetic-device-passcode")
        await flow.task
        assert flow.visible("owner")=={"phase":"complete","item_count":1}
        assert saved[0].name=="Keys"
        assert saved[0].identifier=="SYNTHETIC-BEACON"
        assert len(saved[0].keys_at(0))==3
        account.request_pet.assert_awaited_once()
        session.recover.assert_awaited_once_with(whole.circle.peer.record,"synthetic-device-passcode")
    finally:
        await flow.cancel("owner")
        await account._http.close()

@pytest.mark.asyncio
async def test_owned_composition_guards_all_clients_and_denies_write_methods(monkeypatch):
    from test_cloudkit import FakeAccount
    from findmy.cloudkit.client import AsyncCloudKitClient
    from findmy_home.owned_protocol import open_shared_client
    from findmy_home.apple_transport import TransportBlocked
    account=FakeAccount();account.request_pet=AsyncMock(return_value="synthetic-pet")
    seen=[]
    async def container(client):
        assert isinstance(client._http,OwnedHttpSession)
        assert client._http.profile=="cloudkit"
        seen.append(client)
        return SimpleNamespace(partition="24",database_gateway_url="https://gateway.icloud.com/ckdatabase",code_gateway_url="https://gateway.icloud.com/ckcoderouter")
    monkeypatch.setattr(AsyncCloudKitClient,"open_container",container)
    client=await open_shared_client(account)
    try:
        for sdk_client in (client.store.client,client.session._cloudkit,client.session._cuttlefish,client.session._securityd):
            assert isinstance(sdk_client._http,OwnedHttpSession)
            assert sdk_client._http.profile=="cloudkit"
        assert client.session._proxy._http.profile=="escrow"
        with pytest.raises(TransportBlocked):
            await client.session._cuttlefish.function_invoke("Cuttlefish","joinWithVoucher",b"synthetic")
        with pytest.raises(TransportBlocked):
            await client.store.client._http.post("https://gateway.icloud.com/ckdatabase/api/client/record/save",data=b"synthetic-key")
    finally: await client.close()
    assert all(item._http._closed for item in seen)

@pytest.mark.asyncio
async def test_cancellation_during_initial_container_open_closes_all_owned_transports(monkeypatch):
    import asyncio
    from test_cloudkit import FakeAccount
    from findmy.cloudkit.client import AsyncCloudKitClient
    from findmy_home.owned_protocol import open_shared_client
    captured=[];entered=asyncio.Event()
    original=OwnedHttpSession.__init__
    def init(transport,**kwargs):
        original(transport,**kwargs);captured.append(transport)
    async def blocked(client):
        entered.set();await asyncio.Event().wait()
    monkeypatch.setattr(OwnedHttpSession,"__init__",init)
    monkeypatch.setattr(AsyncCloudKitClient,"open_container",blocked)
    task=asyncio.create_task(open_shared_client(FakeAccount()))
    await asyncio.wait_for(entered.wait(),1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert len(captured)==3
    assert all(transport._closed for transport in captured)

@pytest.mark.asyncio
async def test_server_supplied_third_party_gateway_is_rejected_before_operation(monkeypatch):
    from test_cloudkit import FakeAccount
    from findmy.cloudkit.client import AsyncCloudKitClient
    from findmy_home.owned_protocol import open_shared_client
    from findmy_home.apple_transport import TransportBlocked
    account=FakeAccount();account.request_pet=AsyncMock(return_value="synthetic-pet")
    async def metadata(client):
        return SimpleNamespace(partition="24",database_gateway_url="https://evil.invalid/ckdatabase",code_gateway_url="https://gateway.icloud.com/ckcoderouter")
    monkeypatch.setattr(AsyncCloudKitClient,"open_container",metadata)
    with pytest.raises(TransportBlocked):await open_shared_client(account)
    account.request_pet.assert_not_awaited()

@pytest.mark.asyncio
async def test_real_sdk_container_request_uses_owned_routing_and_rejects_untrusted_reply(monkeypatch):
    import json
    from test_cloudkit import FakeAccount,app_init_response
    from findmy_home.owned_protocol import open_shared_client
    from findmy_home.apple_transport import TransportBlocked
    metadata=app_init_response().json()
    metadata["cloudKitDatabaseGatewayUrl"]="https://third-party.invalid/collect"
    calls=[]
    class Reply:
        status=200
        headers={}
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        @property
        def content(self):return self
        async def iter_chunked(self,size):yield json.dumps(metadata).encode()
    class Session:
        def request(self,method,url,**kwargs):
            calls.append((method,url,kwargs))
            return Reply()
    async def connection(transport,host):
        assert host=="gateway.icloud.com"
        return Session()
    monkeypatch.setattr(OwnedHttpSession,"_session",connection)
    account=FakeAccount();account.request_pet=AsyncMock(return_value="synthetic-pet")
    with pytest.raises(TransportBlocked):await open_shared_client(account)
    assert len(calls)==1
    assert calls[0][1]=="https://gateway.icloud.com/setup/setup/ck/v1/ckAppInit?container=com.apple.icloud.searchparty"
    assert calls[0][2]["allow_redirects"] is False
    assert calls[0][2]["headers"]["x-cloudkit-authtoken"]=="ck-token"
    account.request_pet.assert_not_awaited()

@pytest.mark.asyncio
async def test_owned_account_transport_is_installed_before_authentication(monkeypatch,tmp_path):
    import hashlib
    from findmy_home.offline_signer import OfflineSigner,provider_for
    from findmy_home.owned_protocol import create_account
    path=tmp_path/"library";path.write_bytes(b"synthetic-library")
    signer=OfflineSigner(path,b"synthetic-existing-state",hashlib.sha256(path.read_bytes()).hexdigest())
    engine=SimpleNamespace(is_provisioned=True,get_data=lambda:{"X-Apple-I-MD":"synthetic-otp","X-Apple-I-MD-M":"synthetic-machine"},
        save_provisioning=lambda stream:stream.write(b"synthetic-existing-state"))
    monkeypatch.setattr("findmy_home.offline_signer._build_engine",lambda state,libraries:engine)
    await signer.initialize()
    provider=provider_for(signer,serial="SYNTHETIC-CLIENT")
    account=await create_account(provider,timeout=17)
    try:
        assert isinstance(account._http,OwnedHttpSession)
        assert account._http.profile=="account"
        assert account._http.timeout==17
        headers=await account.get_anisette_headers()
        assert headers["X-Apple-I-MD"]=="synthetic-otp"
        assert provider._prepared=={}
    finally:await account.close()
    assert not signer.ready

@pytest.mark.asyncio
async def test_default_downloading_or_remote_provider_is_not_admitted():
    from findmy import LocalAnisetteProvider
    from findmy_home.owned_protocol import create_account
    from findmy_home.apple_transport import TransportBlocked
    provider=LocalAnisetteProvider()
    try:
        with pytest.raises(TransportBlocked):await create_account(provider)
    finally:await provider.close()

async def _restored_reporting_account(monkeypatch,tmp_path):
    """Real candidate state serialization + app restore; native engine synthetic."""
    import hashlib
    from findmy.reports.anisette import DeviceIdentity
    from findmy.reports.state import LoginState
    from findmy_home.offline_signer import OfflineSigner,provider_for
    from findmy_home.owned_protocol import create_account
    from findmy_home.owned_session import snapshot_account,restore_account
    library=tmp_path/"reviewed-library";library.write_bytes(b"synthetic-reviewed-library")
    digest=hashlib.sha256(library.read_bytes()).hexdigest()
    engine=SimpleNamespace(is_provisioned=True,get_data=lambda:{"X-Apple-I-MD":"synthetic-otp","X-Apple-I-MD-M":"synthetic-machine"},
        save_provisioning=lambda stream:stream.write(b"synthetic-existing-state"))
    monkeypatch.setattr("findmy_home.offline_signer._build_engine",lambda state,libraries:engine)
    signer=OfflineSigner(library,b"synthetic-existing-state",digest);await signer.initialize()
    identity=DeviceIdentity(model="SyntheticModel1,1",os_name="SyntheticOS",os_version="1.2",os_build="SYNTHETIC",cfnetwork="1",darwin="1")
    source=await create_account(provider_for(signer,serial="SYNTHETIC-RESTORE",identity=identity))
    source._username="synthetic@example.invalid";source._password="synthetic-transient-password"
    source._set_login_state(LoginState.LOGGED_IN,{"dsid":"12345","adsid":"56789","mobileme_data":{"tokens":{
        "searchPartyToken":"synthetic-report-token","cloudKitToken":"synthetic-cloudkit-token"}},
        "idms_pet":"synthetic-pet-not-for-disk","idms_hb":"synthetic-heartbeat-not-for-disk"})
    before=source.to_json()
    key=b"s"*32
    try:envelope=await snapshot_account(source,encryption_key=key,expires_at=2000,now=1000)
    finally:await source.close()
    # The SDK generic deserializer must never be used by restoration.
    from findmy import AsyncAppleAccount
    monkeypatch.setattr(AsyncAppleAccount,"from_json",lambda *args,**kwargs:pytest.fail("legacy account restore used"))
    restored=await restore_account(envelope,encryption_key=key,library=library,expected_sha256=digest,now=1001,timeout=17)
    after=restored.to_json()
    assert after["ids"]==before["ids"]
    assert after["anisette"]["identity"]==identity.to_json()
    assert after["anisette"]["serial"]=="SYNTHETIC-RESTORE"
    assert after["account"]["password"] is None
    assert "idms_pet" not in after["login"]["data"] and "idms_hb" not in after["login"]["data"]
    assert restored.service_tokens==before["login"]["data"]["mobileme_data"]["tokens"]
    return restored


def _report_reply(monkeypatch,*,status,body):
    """Keep owned request construction, validation and redirect policy active."""
    calls=[]
    class Reply:
        headers={}
        def __init__(self):self.status=status
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        @property
        def content(self):return self
        async def iter_chunked(self,size):yield body
    class Session:
        def request(self,method,url,**kwargs):calls.append((method,url,kwargs));return Reply()
    async def connection(transport,host):
        assert transport.profile=="account" and host=="gateway.icloud.com"
        return Session()
    monkeypatch.setattr(OwnedHttpSession,"_session",connection)
    return calls

@pytest.mark.asyncio
async def test_real_session_roundtrip_preserves_reporting_class_identity_and_owned_requests(monkeypatch,tmp_path):
    from findmy_home.apple import ReportingAccount
    restored=await _restored_reporting_account(monkeypatch,tmp_path)
    calls=_report_reply(monkeypatch,status=200,body=b'{"acsnLocations":{"statusCode":"200","locationPayload":[]}}')
    try:
        assert isinstance(restored,ReportingAccount)
        assert isinstance(restored._http,OwnedHttpSession) and restored._http.timeout==17
        assert await restored.fetch_raw_reports([(["synthetic-key"],[])])==[]
        assert len(calls)==1
        method,url,kwargs=calls[0]
        assert method=="POST" and url=="https://gateway.icloud.com/findmyservice/v2/fetch"
        assert (kwargs["auth"].login,kwargs["auth"].password)==("12345","synthetic-report-token")
        assert kwargs["headers"]["X-Apple-I-MD"]=="synthetic-otp"
        assert kwargs["allow_redirects"] is False
    finally:await restored.close()
    assert not restored._anisette._owned_signer.ready and restored._http._closed

@pytest.mark.asyncio
async def test_restored_report_rejection_requires_reauth_without_login_or_pet_retry(monkeypatch,tmp_path):
    from findmy.errors import UnauthorizedError
    restored=await _restored_reporting_account(monkeypatch,tmp_path)
    calls=_report_reply(monkeypatch,status=401,body=b"{}")
    login=AsyncMock(side_effect=AssertionError("restored account attempted login"))
    monkeypatch.setattr(restored,"_gsa_authenticate",login)
    try:
        with pytest.raises(UnauthorizedError):await restored.fetch_raw_reports([(["synthetic-key"],[])])
        assert len(calls)==1
        login.assert_not_awaited()
        assert restored._password is None
    finally:await restored.close()

@pytest.mark.asyncio
async def test_restored_reporting_empty_response_retains_app_error_classification(monkeypatch,tmp_path):
    from findmy_home.apple import ReportSourceUnavailable
    restored=await _restored_reporting_account(monkeypatch,tmp_path)
    calls=_report_reply(monkeypatch,status=200,body=b"")
    # The candidate performs bounded async empty-body retries. Skip only the wait,
    # not request construction or the ReportingAccount classification boundary.
    monkeypatch.setattr("findmy.reports.account.asyncio.sleep",AsyncMock())
    try:
        with pytest.raises(ReportSourceUnavailable,match="empty_response"):
            await restored.fetch_raw_reports([(["synthetic-key"],[])])
        assert len(calls)==6
    finally:await restored.close()


@pytest.mark.asyncio
async def test_complete_encrypted_backup_restores_after_original_directory_removed(monkeypatch,tmp_path):
    import hashlib,shutil
    from findmy_home.private_session_store import PrivateSessionStore,restore_reporting_account
    from findmy_home.storage import Store
    root=tmp_path/"original";original=Store(root)
    source=await _restored_reporting_account(monkeypatch,root)
    identity=source.to_json()["ids"]
    library=root/"ani_libs.bin";shutil.copyfile(root/"reviewed-library",library)
    library.chmod(0o600)
    private=PrivateSessionStore(root,library=library,expected_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    try:await private.save(source)
    finally:await source.close()
    target=tmp_path/"restored";shutil.copytree(root,target)
    shutil.rmtree(root)
    assert Store(target).identity==original.identity
    restored=await restore_reporting_account(target)
    calls=_report_reply(monkeypatch,status=200,body=b'{"acsnLocations":{"statusCode":"200","locationPayload":[]}}')
    try:
        assert restored.to_json()["ids"]==identity
        assert restored._password is None
        assert await restored.fetch_raw_reports([(["synthetic-key"],[])])==[]
        assert len(calls)==1
    finally:await restored.close()

@pytest.mark.asyncio
async def test_mixed_encrypted_generations_and_missing_backup_key_fail_closed(monkeypatch,tmp_path):
    import hashlib,json
    from findmy_home.private_session_store import PrivateSessionStore,restore_reporting_account
    from findmy_home.owned_session import SessionBlocked
    from findmy_home.storage import atomic_json
    source=await _restored_reporting_account(monkeypatch,tmp_path)
    library=tmp_path/"ani_libs.bin";library.write_bytes((tmp_path/"reviewed-library").read_bytes());library.chmod(0o600)
    private=PrivateSessionStore(tmp_path,library=library,expected_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    try:
        await private.save(source)
        first=json.loads((tmp_path/"owned-session.json").read_text())["generation"]
        await private.save(source)
        second=json.loads((tmp_path/"owned-session.json").read_text())["generation"]
    finally:await source.close()
    # An older legacy file must not mask damage to the authoritative owned mode.
    atomic_json(tmp_path/"account.json",{"fixture":"legacy-must-not-load"})
    newkey=tmp_path/("session-"+second+".key")
    newkey.write_bytes((tmp_path/("session-"+first+".key")).read_bytes())
    with pytest.raises(SessionBlocked):await restore_reporting_account(tmp_path)
    newkey.unlink()
    with pytest.raises(SessionBlocked):await restore_reporting_account(tmp_path)

@pytest.mark.asyncio
@pytest.mark.parametrize("existing",[True,False])
async def test_shared_startup_factory_preserves_full_identity_with_real_candidate(monkeypatch,tmp_path,existing):
    """Real SDK construction, synthetic native state; no Apple/native execution."""
    from findmy_home import shared_runtime
    from findmy_home.offline_signer import OfflineSigner
    from findmy_home.storage import Store
    from findmy.reports.anisette import CLIENT_IDENTITY
    import hashlib
    import uuid
    state=b"synthetic-private-provisioning-state"
    library=tmp_path/"owned-libs.bin";library.write_bytes(b"synthetic-library")
    digest=hashlib.sha256(library.read_bytes()).hexdigest()
    ids={"uid":str(uuid.uuid4()),"devid":str(uuid.uuid4())}
    serial="b"*32
    store=Store(tmp_path)
    if existing:shared_runtime.SigningIdentityStore(tmp_path,digest).save(state,serial,CLIENT_IDENTITY.to_json(),ids)
    class SyntheticProcessSigner(OfflineSigner):
        async def initialize(self):self._engine=SimpleNamespace(is_provisioned=True);self._state=None
        def snapshot(self):return state
    monkeypatch.setattr(shared_runtime,"require_shared_backend",lambda:None)
    monkeypatch.setattr("findmy_home.native_worker.verify_native_boundary",AsyncMock())
    monkeypatch.setattr("findmy_home.artifact_policy.reviewed_artifact",lambda value,**kwargs:SimpleNamespace(expected_sha256=digest))
    monkeypatch.setattr("findmy_home.artifact_policy.verify_artifact",AsyncMock())
    monkeypatch.setattr("findmy_home.native_worker.ProcessOfflineSigner",SyntheticProcessSigner)
    provision=AsyncMock(return_value=state)
    monkeypatch.setattr("findmy_home.controlled_provisioning.provision_new_identity",provision)
    monkeypatch.setattr("findmy_home.native_worker.IsolatedNativeWorker",lambda **kwargs:SimpleNamespace(identity=kwargs))
    worker,bridge=await shared_runtime.compose_runtime(store,{"shared_artifact_id":"applemusic-arm64-v8a","create_new_identity":True})
    first=second=None
    try:
        first=await worker.account_factory()
        second=await worker.account_factory()
        if not existing:
            _,serial,identity,ids=shared_runtime.SigningIdentityStore(tmp_path,digest).load()
            assert identity==CLIENT_IDENTITY.to_json()
        for account in (first,second):
            assert isinstance(account._http,OwnedHttpSession)
            assert account._http.profile=="account"
            assert account.local_user_uuid==ids["uid"]
            assert account.device_uuid==ids["devid"]
            assert account._anisette.serial==serial
            assert account._anisette.identity==CLIENT_IDENTITY
            assert account._password is None
        if existing:provision.assert_not_awaited()
        else:
            provision.assert_awaited_once()
            options=provision.await_args.kwargs
            assert options["worker"].identity["uid"]==ids["uid"]
            assert options["worker"].identity["devid"]==ids["devid"]
            assert options["worker"].identity["client_info"]==first.client_info
            assert options["user_agent"]==CLIENT_IDENTITY.user_agent("akd/1.0")
        assert not worker.session_available() # signing state is not an account session
    finally:
        if first is not None:await first.close()
        if second is not None:await second.close()
        await bridge.close()
