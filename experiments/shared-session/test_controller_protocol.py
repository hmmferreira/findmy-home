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
