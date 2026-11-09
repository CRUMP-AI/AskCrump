"""SSRF pinning tests for the browser.read fetch path.

These drive the *default* client path (no injected ``http_client``):
validation resolves a hostname once, and the fetch must connect to
that validated address even if a later DNS answer would differ.
The inner transport is a recording ``httpx.MockTransport``, so no
real network or DNS is ever touched: the host a request was sent to
is the address the transport was asked to connect to.
"""
import asyncio

import httpx
import pytest

from backend.browser_agent import (
    BrowserAgent,
    BrowserAgentError,
    _PinnedAsyncTransport,
    _make_pinned_client,
)

USER_ID = '11111111-1111-1111-1111-111111111111'

PUBLIC_IP = '93.184.216.34'
PRIVATE_IP = '10.0.0.5'
METADATA_IP = '169.254.169.254'

PAGE_HTML = (
    '<html><head><title>Pinned Page</title></head>'
    '<body><p>Pinned body text.</p></body></html>'
)


class RecordingTransport:
    """MockTransport wrapper that records where requests were sent."""

    def __init__(self, handler):
        self.seen = []
        self._transport = httpx.MockTransport(self._record(handler))

    def _record(self, handler):
        def recording_handler(request):
            self.seen.append(
                {
                    'url_host': request.url.host,
                    'url': str(request.url),
                    'host_header': request.headers.get('host'),
                    'sni_hostname': request.extensions.get('sni_hostname'),
                }
            )
            return handler(request)

        return recording_handler

    def as_transport(self):
        return self._transport


def _handler(request):
    # Routing keys off the Host header: on the pinned path the URL
    # host is the validated IP, while Host keeps the original name.
    host = request.headers.get('host')
    path = request.url.path
    if host == 'example.com' and path == '/page':
        return httpx.Response(
            200,
            headers={'content-type': 'text/html; charset=utf-8'},
            content=PAGE_HTML,
        )
    if host == 'example.com' and path == '/to-private':
        return httpx.Response(
            302, headers={'location': 'http://internal.example.com/secret'}
        )
    if host == 'example.com' and path == '/chain':
        return httpx.Response(
            302, headers={'location': 'https://example.org/page'}
        )
    if host == 'example.org' and path == '/page':
        return httpx.Response(
            200,
            headers={'content-type': 'text/html'},
            content=b'<html><head><title>Second Host</title></head>'
            b'<body><p>Second host body.</p></body></html>',
        )
    if host == 'internal.example.com' and path == '/secret':
        return httpx.Response(
            200, headers={'content-type': 'text/html'}, content=b'<p>secret</p>'
        )
    return httpx.Response(
        404, headers={'content-type': 'text/html'}, content=b'not found'
    )


def _pinned_agent(resolver, recording):
    return BrowserAgent(
        resolver=resolver, transport=recording.as_transport()
    )


def test_rebinding_answer_after_validation_is_never_connected_to():
    calls = []

    def rebinding_resolver(hostname):
        calls.append(hostname)
        if len(calls) == 1:
            return [PUBLIC_IP]
        return [PRIVATE_IP]

    recording = RecordingTransport(_handler)
    agent = _pinned_agent(rebinding_resolver, recording)
    page = asyncio.run(agent.read_page(USER_ID, 'https://example.com/page'))

    assert page['finalUrl'] == 'https://example.com/page'
    assert page['title'] == 'Pinned Page'
    assert 'Pinned body text.' in page['text']
    # Validation resolved exactly once for this hop, and the fetch
    # connected only to that validated address.
    assert calls == ['example.com']
    assert [seen['url_host'] for seen in recording.seen] == [PUBLIC_IP]
    assert all(seen['url_host'] != PRIVATE_IP for seen in recording.seen)
    # The original hostname survives for Host and for TLS SNI.
    assert recording.seen[0]['host_header'] == 'example.com'
    assert recording.seen[0]['sni_hostname'] == 'example.com'


def test_metadata_address_is_blocked_before_any_fetch():
    def metadata_resolver(hostname):
        return [METADATA_IP]

    recording = RecordingTransport(_handler)
    agent = _pinned_agent(metadata_resolver, recording)
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(
            agent.read_page(USER_ID, 'https://metadata.example.com/latest')
        )
    assert caught.value.code == 'BROWSER_URL_BLOCKED'
    assert recording.seen == []

    with pytest.raises(BrowserAgentError) as literal:
        asyncio.run(
            agent.read_page(
                USER_ID, 'http://169.254.169.254/latest/meta-data/'
            )
        )
    assert literal.value.code == 'BROWSER_URL_BLOCKED'
    assert recording.seen == []


def test_redirect_hop_resolving_private_is_blocked_and_never_fetched():
    addresses = {
        'example.com': [PUBLIC_IP],
        'internal.example.com': ['192.168.1.20'],
    }
    recording = RecordingTransport(_handler)
    agent = _pinned_agent(
        lambda hostname: list(addresses.get(hostname, [])), recording
    )
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(agent.read_page(USER_ID, 'https://example.com/to-private'))
    assert caught.value.code == 'BROWSER_URL_BLOCKED'
    # Only the first, public hop was fetched; the private destination
    # was blocked at validation and never reached the transport.
    assert [seen['url_host'] for seen in recording.seen] == [PUBLIC_IP]
    assert recording.seen[0]['host_header'] == 'example.com'


def test_redirect_hop_is_repinned_to_its_own_validated_address():
    addresses = {
        'example.com': [PUBLIC_IP],
        'example.org': ['93.184.216.35'],
    }
    recording = RecordingTransport(_handler)
    agent = _pinned_agent(
        lambda hostname: list(addresses.get(hostname, [])), recording
    )
    page = asyncio.run(agent.read_page(USER_ID, 'https://example.com/chain'))
    assert page['finalUrl'] == 'https://example.org/page'
    assert page['title'] == 'Second Host'
    assert [seen['url_host'] for seen in recording.seen] == [
        PUBLIC_IP,
        '93.184.216.35',
    ]
    assert [seen['host_header'] for seen in recording.seen] == [
        'example.com',
        'example.org',
    ]
    assert [seen['sni_hostname'] for seen in recording.seen] == [
        'example.com',
        'example.org',
    ]


def test_pinned_transport_refuses_a_request_for_another_host():
    recording = RecordingTransport(_handler)
    transport = _PinnedAsyncTransport(
        'example.com', PUBLIC_IP, inner=recording.as_transport()
    )

    async def drive():
        client = httpx.AsyncClient(
            transport=transport, trust_env=False, timeout=5
        )
        try:
            await client.get('https://other.example.net/page')
        finally:
            await client.aclose()

    with pytest.raises(httpx.ConnectError):
        asyncio.run(drive())
    assert recording.seen == []


def test_real_client_and_transport_disable_trust_env(monkeypatch):
    for name in (
        'HTTP_PROXY',
        'HTTPS_PROXY',
        'ALL_PROXY',
        'http_proxy',
        'https_proxy',
        'all_proxy',
    ):
        monkeypatch.setenv(name, 'http://proxy.example.com:8080')
    monkeypatch.setenv('NO_PROXY', '')
    monkeypatch.setenv('no_proxy', '')

    transport = _PinnedAsyncTransport('example.com', PUBLIC_IP)
    try:
        assert transport.trust_env is False
        assert isinstance(transport.inner, httpx.AsyncHTTPTransport)
    finally:
        asyncio.run(transport.aclose())

    client = _make_pinned_client('example.com', PUBLIC_IP)
    try:
        assert client.trust_env is False
        assert isinstance(client._transport, _PinnedAsyncTransport)
        assert client._transport.trust_env is False
        assert client._transport.address == PUBLIC_IP
        assert client._transport.hostname == 'example.com'
        # No environment proxy mounts were picked up.
        assert client._mounts == {}
    finally:
        asyncio.run(client.aclose())


def test_multicast_addresses_are_blocked_before_any_fetch():
    # Multicast answers report as ``is_global`` on Python 3.12, but
    # they are not public unicast destinations and must be blocked
    # like every other non-public answer.
    recording = RecordingTransport(_handler)

    agent = _pinned_agent(lambda hostname: ['224.0.0.1'], recording)
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(agent.read_page(USER_ID, 'https://example.com/page'))
    assert caught.value.code == 'BROWSER_URL_BLOCKED'

    agent = _pinned_agent(lambda hostname: ['ff02::1'], recording)
    with pytest.raises(BrowserAgentError) as caught_v6:
        asyncio.run(agent.read_page(USER_ID, 'https://example.com/page'))
    assert caught_v6.value.code == 'BROWSER_URL_BLOCKED'

    agent = _pinned_agent(lambda hostname: [PUBLIC_IP], recording)
    with pytest.raises(BrowserAgentError) as literal:
        asyncio.run(agent.read_page(USER_ID, 'http://224.0.0.1/page'))
    assert literal.value.code == 'BROWSER_URL_BLOCKED'

    assert recording.seen == []


def test_redirect_hop_rebinding_to_private_is_blocked():
    # The same hostname answers public for the first hop and private
    # when the redirect hop is resolved: per-hop re-validation must
    # block the second fetch even though the host was fine before.
    calls = []

    def flipping_resolver(hostname):
        calls.append(hostname)
        if len(calls) == 1:
            return [PUBLIC_IP]
        return [PRIVATE_IP]

    def flip_handler(request):
        host = request.headers.get('host')
        path = request.url.path
        if host == 'example.com' and path == '/flip':
            return httpx.Response(
                302, headers={'location': 'https://example.com/target'}
            )
        if host == 'example.com' and path == '/target':
            return httpx.Response(
                200,
                headers={'content-type': 'text/html'},
                content=b'<p>must never be fetched</p>',
            )
        return _handler(request)

    recording = RecordingTransport(flip_handler)
    agent = _pinned_agent(flipping_resolver, recording)
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(agent.read_page(USER_ID, 'https://example.com/flip'))
    assert caught.value.code == 'BROWSER_URL_BLOCKED'
    assert calls == ['example.com', 'example.com']
    assert [seen['url_host'] for seen in recording.seen] == [PUBLIC_IP]


def test_idn_hostname_fetches_through_the_pin():
    # The shared handler routes on ASCII hostnames, so this test
    # answers any pinned request with the page and asserts on what
    # the recording captured instead.
    recording = RecordingTransport(
        lambda request: httpx.Response(
            200,
            headers={'content-type': 'text/html; charset=utf-8'},
            content=PAGE_HTML,
        )
    )
    agent = _pinned_agent(lambda hostname: [PUBLIC_IP], recording)
    page = asyncio.run(agent.read_page(USER_ID, 'https://münchen.example/page'))
    assert page['title'] == 'Pinned Page'
    assert [seen['url_host'] for seen in recording.seen] == [PUBLIC_IP]
    assert recording.seen[0]['host_header'] == 'xn--mnchen-3ya.example'
    assert recording.seen[0]['sni_hostname'] == 'xn--mnchen-3ya.example'


def test_ipv6_answer_is_pinned():
    recording = RecordingTransport(_handler)
    agent = _pinned_agent(
        lambda hostname: ['2606:4700:4700::1111'], recording
    )
    page = asyncio.run(agent.read_page(USER_ID, 'https://example.com/page'))
    assert page['title'] == 'Pinned Page'
    assert [seen['url_host'] for seen in recording.seen] == [
        '2606:4700:4700::1111'
    ]
    assert recording.seen[0]['url'].startswith(
        'https://[2606:4700:4700::1111]/'
    )
    assert recording.seen[0]['host_header'] == 'example.com'
    assert recording.seen[0]['sni_hostname'] == 'example.com'


# --- Real-socket proofs -------------------------------------------------
# The tests above stop at a MockTransport, which proves the wiring at
# the httpx transport boundary but not that the real httpcore stack
# honours the pin. The tests below run the pinned transport over a
# real ``AsyncHTTPTransport`` against a local server. They construct
# ``_PinnedAsyncTransport`` directly with a loopback pin: that is the
# test double, not a production path -- ``read_page`` only ever pins
# addresses that passed public validation, and loopback answers are
# rejected there (see the metadata and private tests above).


def test_pinned_transport_connects_to_the_pinned_address_over_a_real_socket():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received['host'] = self.headers.get('Host')
            received['path'] = self.path
            body = b'<html><body><p>real socket</p></body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    async def drive():
        inner = httpx.AsyncHTTPTransport(trust_env=False)
        transport = _PinnedAsyncTransport(
            'example.com', '127.0.0.1', inner=inner
        )
        try:
            async with httpx.AsyncClient(
                transport=transport, trust_env=False, timeout=5
            ) as client:
                return await client.get(f'http://example.com:{port}/page')
        finally:
            await inner.aclose()

    try:
        response = asyncio.run(drive())
    finally:
        server.shutdown()
        thread.join(timeout=5)

    # The URL names example.com, whose real addresses are not this
    # loopback server: the request can only have arrived here over
    # the pinned connection, with the original Host header intact.
    assert response.status_code == 200
    assert b'real socket' in response.content
    assert received['path'] == '/page'
    assert received['host'] == f'example.com:{port}'


def _make_test_ca():
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Pin Test CA')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _make_test_leaf(ca_key, ca_cert, dns_name):
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_name)])
        )
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(dns_name)]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _serve_tls(tmp_path, leaf_key, leaf_cert, ca_cert, sni_seen):
    import ssl
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from cryptography.hazmat.primitives import serialization

    key_pem = leaf_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    cert_pem = leaf_cert.public_bytes(serialization.Encoding.PEM)
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    key_path = tmp_path / 'leaf-key.pem'
    cert_path = tmp_path / 'leaf-cert.pem'
    key_path.write_bytes(key_pem)
    cert_path.write_bytes(cert_pem + ca_pem)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))

    def record_sni(_socket, server_name, _context):
        sni_seen.append(server_name)

    context.sni_callback = record_sni

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'ok-tls'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


async def _fetch_pinned_https(port, verify_context):
    inner = httpx.AsyncHTTPTransport(verify=verify_context, trust_env=False)
    transport = _PinnedAsyncTransport('example.com', '127.0.0.1', inner=inner)
    try:
        async with httpx.AsyncClient(
            transport=transport, trust_env=False, timeout=5
        ) as client:
            return await client.get(f'https://example.com:{port}/')
    finally:
        await inner.aclose()


def test_pinned_transport_verifies_the_certificate_against_the_hostname(
    tmp_path,
):
    import ssl

    from cryptography.hazmat.primitives import serialization

    ca_key, ca_cert = _make_test_ca()
    ca_path = tmp_path / 'ca.pem'
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    # The leaf carries a DNS SAN for example.com only -- no IP SAN
    # for the pinned 127.0.0.1 -- so the handshake can only succeed
    # if verification checks the original hostname, not the address
    # the connection was pinned to.
    leaf_key, leaf_cert = _make_test_leaf(ca_key, ca_cert, 'example.com')
    sni_seen = []
    server, thread, port = _serve_tls(
        tmp_path, leaf_key, leaf_cert, ca_cert, sni_seen
    )
    try:
        verify = ssl.create_default_context(cafile=str(ca_path))
        response = asyncio.run(_fetch_pinned_https(port, verify))
    finally:
        server.shutdown()
        thread.join(timeout=5)
    assert response.status_code == 200
    assert response.content == b'ok-tls'
    assert sni_seen == ['example.com']


def test_pinned_transport_rejects_a_certificate_for_another_hostname(
    tmp_path,
):
    import ssl

    from cryptography.hazmat.primitives import serialization

    ca_key, ca_cert = _make_test_ca()
    ca_path = tmp_path / 'ca.pem'
    ca_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    leaf_key, leaf_cert = _make_test_leaf(
        ca_key, ca_cert, 'other.example.com'
    )
    sni_seen = []
    server, thread, port = _serve_tls(
        tmp_path, leaf_key, leaf_cert, ca_cert, sni_seen
    )
    try:
        verify = ssl.create_default_context(cafile=str(ca_path))
        with pytest.raises(httpx.ConnectError):
            asyncio.run(_fetch_pinned_https(port, verify))
    finally:
        server.shutdown()
        thread.join(timeout=5)
    # SNI still carried the original hostname; verification failed
    # against that hostname, not against the pinned address.
    assert sni_seen == ['example.com']
