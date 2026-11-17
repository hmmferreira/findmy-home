"""Our controller over real candidate crypto and synthetic account fixtures."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fake_account import Accessory,a_whole_account
from findmy.icloud import AsyncFindMyClient
from findmy_home.shared_discovery import SharedDiscovery

@pytest.mark.asyncio
async def test_controller_delivers_decrypted_accessories_without_rust_or_second_login(monkeypatch):
    whole=a_whole_account([Accessory(name="Keys",identifier="SYNTHETIC-BEACON")])
    whole.use_the_view(monkeypatch)
    session=whole.circle.session()
    session.recovery_options=AsyncMock(return_value=SimpleNamespace(recoverable=[whole.circle.peer.record]))
    session.recover=AsyncMock(return_value=whole.circle.peer)
    session.close=AsyncMock()
    account=SimpleNamespace(login_state=SimpleNamespace(name="LOGGED_IN"),_password="synthetic-transient-password",
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
    monkeypatch.setattr(AsyncFindMyClient,"open",open_client)
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
    finally: await flow.cancel("owner")
