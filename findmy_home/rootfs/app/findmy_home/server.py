"""Separate ingress management and read-only integration API listeners."""
import asyncio
import hashlib
import hmac
import logging
import os
from pathlib import Path
import secrets
import socket
import time
from aiohttp import web, ClientSession, ClientTimeout
from .storage import Store
from .auth import ExportFlow
from .worker import AppleWorker
from .importer import import_exports
from .descriptions import enrich_metadata

STATIC = Path(__file__).parent / "static"


def csrf(store, owner, bucket=None):
    bucket = int(time.time() // 300) if bucket is None else bucket
    return hmac.new(store.identity["csrf_key"].encode(), f"{owner}:{bucket}".encode(), hashlib.sha256).hexdigest()


def make_app(store, *, management=False, trusted_peer="172.30.32.2", flow=None, worker=None):
    flow = flow or ExportFlow(store.root)
    worker = worker or AppleWorker(store)

    @web.middleware
    async def security(request, handler):
        if management:
            groups = {group.strip() for group in request.headers.get("X-Remote-User-Groups", "").split(",")}
            if (request.remote != trusted_peer or not request.headers.get("X-Remote-User-Id")
                    or "system-admin" not in groups):
                raise web.HTTPForbidden()
            if request.method != "GET":
                supplied = request.headers.get("X-CSRF-Token", "")
                owner = request.headers["X-Remote-User-Id"]
                bucket = int(time.time() // 300)
                if not any(secrets.compare_digest(supplied, csrf(store, owner, n)) for n in (bucket, bucket - 1)):
                    raise web.HTTPForbidden()
                if request.content_type != "application/json":
                    raise web.HTTPUnsupportedMediaType()
        elif not secrets.compare_digest(request.headers.get("Authorization", ""), "Bearer " + store.identity["read_token"]):
            raise web.HTTPUnauthorized()
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        except (ValueError, KeyError, TypeError):
            response = web.json_response({"error": "invalid_request", "message": "Check the current step and try again."}, status=400)
        except Exception:
            response = web.json_response({"error": "operation_failed", "message": "The operation failed. You can retry or reconnect your account."}, status=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        return response

    app = web.Application(middlewares=[security], client_max_size=4096)

    async def snapshot(request):
        data = store.public()
        if management:
            owner = request.headers["X-Remote-User-Id"]
            data.update(csrf=csrf(store, owner), recovery=flow.visible(owner),
                        setup={"locations_connected":(store.root/"account.json").exists() and store.health.get("status")!="reauth_required",
                               "discovery_session_saved":(store.root/"export/state/exporter-session.plist").exists()})
        return web.json_response(data)

    app.router.add_get("/v1/snapshot", snapshot)
    if not management:
        return app

    async def index(request):
        return web.FileResponse(STATIC / "index.html")

    async def select(request):
        data = await request.json()
        store.select(data["ids"])
        worker.request_poll()
        return web.json_response({"saved": True, "selected_count":len(data["ids"]),
                                  "message":"Tracking choices saved."})

    async def login(request):
        data = await request.json()
        email, password = data["email"], data["password"]
        if not isinstance(email, str) or not isinstance(password, str) or not (0 < len(email) <= 254 and 0 < len(password) <= 512):
            raise ValueError()
        return web.json_response(await worker.login(request.headers["X-Remote-User-Id"], email, password))

    async def factor(request):
        data = await request.json()
        code = data.get("code")
        if code is not None and (not isinstance(code, str) or not code.isdigit() or not 4 <= len(code) <= 8):
            raise ValueError()
        return web.json_response(await worker.factor(request.headers["X-Remote-User-Id"], data["method"], code))

    async def recovery(request):
        owner = request.headers["X-Remote-User-Id"]
        data = await request.json()
        if data["action"] == "start":
            if data.get("consent") is not True:
                raise ValueError()
            credentials=data.get("credentials")
            if credentials is not None and not isinstance(credentials,dict):
                raise ValueError()
            if not isinstance(data.get("fresh_login",False),bool):
                raise ValueError()
            await flow.start(owner,credentials=credentials,fresh_login=data.get("fresh_login",False))
        elif data["action"] == "answer":
            await flow.answer(owner, data["value"])
        elif data["action"] == "cancel":
            await flow.cancel(owner)
        else:
            raise ValueError()
        if flow.state["phase"] == "complete":
            await asyncio.to_thread(import_exports, store, store.root / "export" / "accessories")
        return web.json_response(flow.visible(owner))

    async def refresh_item(request):
        data=await request.json()
        if not isinstance(data.get("id"),str):
            raise ValueError()
        return web.json_response(worker.request_refresh(data["id"]))

    async def cancel(request):
        await worker.cancel(request.headers["X-Remote-User-Id"])
        return web.json_response({"phase": "cancelled"})

    app.router.add_get("/", index)
    app.router.add_static("/static", STATIC)
    app.router.add_post("/ui/select", select)
    app.router.add_post("/ui/refresh", refresh_item)
    app.router.add_post("/ui/login", login)
    app.router.add_post("/ui/factor", factor)
    app.router.add_post("/ui/cancel", cancel)
    app.router.add_post("/ui/recovery", recovery)
    return app


async def announce(store):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    async with ClientSession(timeout=ClientTimeout(total=15)) as session:
        async with session.post("http://supervisor/discovery", headers={"Authorization": "Bearer " + token},
            json={"service": "findmy_home", "config": {"host": socket.gethostname(), "port": 8100,
                  "token": store.identity["read_token"], "instance_id": store.identity["instance_id"], "channel":store.channel}}) as response:
            return response.status == 200


async def main():
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    store = Store(Path(os.environ.get("FINDMY_HOME_DATA", "/data/findmy_home")))
    await asyncio.to_thread(enrich_metadata,store)
    flow, worker = ExportFlow(store.root), AppleWorker(store)
    ui = web.AppRunner(make_app(store, management=True, flow=flow, worker=worker), access_log=None)
    api = web.AppRunner(make_app(store), access_log=None)
    await ui.setup()
    await api.setup()
    await web.TCPSite(ui, "0.0.0.0", 8099).start()
    await web.TCPSite(api, "0.0.0.0", 8100).start()
    async def announcements():
        while True:
            try:
                await announce(store)
            except Exception:
                pass
            await asyncio.sleep(300)
    tasks = [asyncio.create_task(worker.run()), asyncio.create_task(announcements())]
    try:
        await asyncio.Event().wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await flow.cancel(flow.owner)
        await worker.close()
        await worker.cancel(worker.owner)
        await api.cleanup()
        await ui.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
