"""Single-flight polling; passwords discarded after authentication."""
import asyncio
from datetime import datetime, timezone, timedelta
import math
import time
from .storage import atomic_json, read_json, token_only


class AppleWorker:
    def __init__(self, store):
        self.store = store
        self.lock = asyncio.Lock()
        self.pending = None
        self.owner = None
        self.methods = []
        self.auth_task = None
        self.failures = 0

    def _session(self, account):
        atomic_json(self.store.root / "account.json", token_only(account))

    async def _clear_pending(self):
        if self.pending:
            await self.pending.close()
        self.pending, self.owner, self.methods = None, None, []
        if self.auth_task and self.auth_task is not asyncio.current_task():
            self.auth_task.cancel()
        self.auth_task = None

    async def _expire(self):
        await asyncio.sleep(600)
        async with self.lock:
            await self._clear_pending()

    async def login(self, owner, email, password):
        from findmy import AsyncAppleAccount, LocalAnisetteProvider, LoginState
        async with self.lock:
            if self.pending:
                raise ValueError("Finish or cancel the current sign-in")
            account = AsyncAppleAccount(LocalAnisetteProvider(libs_path=str(self.store.root / "ani_libs.bin")))
            self.pending, self.owner = account, owner
            self.auth_task = asyncio.create_task(self._expire())
            try:
                async with asyncio.timeout(90):
                    state = await account.login(email, password)
                    if state == LoginState.REQUIRE_2FA:
                        self.methods = list(await account.get_2fa_methods())
                        return {"phase": "choose_method", "methods": [
                            {"value": n, "label": "SMS" if "Sms" in type(m).__name__ else "Trusted device"}
                            for n, m in enumerate(self.methods)]}
                    if state != LoginState.LOGGED_IN:
                        raise ValueError("Authentication incomplete")
                    self._session(account)
                    await self._clear_pending()
                    self.store.health["status"] = "ready"
                    return {"phase": "complete"}
            except Exception:
                await self._clear_pending()
                raise

    async def factor(self, owner, index, code=None):
        from findmy import LoginState
        async with self.lock:
            if not self.pending or self.owner != owner:
                raise ValueError("No active sign-in for this user")
            if not isinstance(index, int) or index < 0 or index >= len(self.methods):
                raise ValueError("Invalid verification method")
            try:
                async with asyncio.timeout(90):
                    method = self.methods[index]
                    if code is None:
                        await method.request()
                        return {"phase": "verification_code", "method": index}
                    await method.submit(code)
                    if self.pending.login_state != LoginState.LOGGED_IN:
                        raise ValueError("Verification incomplete")
                    self._session(self.pending)
                    await self._clear_pending()
                    self.store.health["status"] = "ready"
                    return {"phase": "complete"}
            except Exception:
                await self._clear_pending()
                raise

    async def cancel(self, owner):
        async with self.lock:
            if self.owner and self.owner != owner:
                raise ValueError("Sign-in belongs to another user")
            await self._clear_pending()

    async def poll(self):
        from findmy import AsyncAppleAccount, FindMyAccessory
        from findmy.errors import InvalidCredentialsError
        async with self.lock:
            if self.pending:
                return
            selected = {key: item for key, item in self.store.items.items() if item["enabled"]}
            session = read_json(self.store.root / "account.json")
            if session is None:
                self.store.health["status"] = "reauth_required"
                return
            if not selected:
                self.store.health["status"] = "select_items"
                return
            try:
                await asyncio.to_thread(self._poll_thread, session, selected)
            except Exception as error:
                self.failures += 1
                self.store.health["status"] = "reauth_required" if isinstance(error, (InvalidCredentialsError,)) or (isinstance(error, ValueError) and str(error) == "No username or password specified") else "error"

    def _poll_thread(self, session, selected):
        asyncio.run(self._fetch(session, selected))

    async def _fetch(self, session, selected):
        from findmy import AsyncAppleAccount, FindMyAccessory
        from findmy.errors import InvalidCredentialsError
        account = AsyncAppleAccount.from_json(session, anisette_libs_path=str(self.store.root / "ani_libs.bin"))
        try:
            accessories = [FindMyAccessory.from_json(self.store.root / "keys" / item["key_file"])
                           for item in selected.values()]
            self.store.health["status"] = "polling"
            async with asyncio.timeout(600):
                reports = await account.fetch_location(accessories)
            self._session(account)
            for (key, item), accessory in zip(selected.items(), accessories):
                atomic_json(self.store.root / "keys" / item["key_file"], accessory.to_json())
                report = reports.get(accessory)
                if report is None:
                    continue
                lat, lon, accuracy = report.latitude, report.longitude, report.horizontal_accuracy
                if not all(math.isfinite(v) for v in (lat, lon, accuracy)) or not (-90 <= lat <= 90 and -180 <= lon <= 180 and accuracy >= 0):
                    continue
                timestamp = report.timestamp.astimezone(timezone.utc)
                previous = self.store.reports.get(key)
                if timestamp > datetime.now(timezone.utc) + timedelta(minutes=5):
                    continue
                if previous and timestamp < datetime.fromisoformat(previous["timestamp"]):
                    continue
                self.store.reports[key] = {"latitude": lat, "longitude": lon, "accuracy": accuracy,
                                           "timestamp": timestamp.isoformat()}
            atomic_json(self.store.root / "reports.json", self.store.reports)
            self.failures = 0
            self.store.health.update(status="ok", last_poll=datetime.now(timezone.utc).isoformat())
        except InvalidCredentialsError:
            self.store.health["status"] = "reauth_required"
        except Exception as error:
            self.failures += 1
            self.store.health["status"] = "reauth_required" if isinstance(error, ValueError) and str(error) == "No username or password specified" else "error"
        finally:
            await account.close()
    async def run(self):
        while True:
            try:
                await self.poll()
            except Exception:
                self.failures += 1
                self.store.health["status"] = "error"
            delay = min(3600, 900 * 2 ** min(self.failures, 2))
            self.store.health["next_poll"] = datetime.fromtimestamp(time.time() + delay, timezone.utc).isoformat()
            await asyncio.sleep(delay)
