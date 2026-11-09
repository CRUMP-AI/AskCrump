import asyncio
import json

import httpx
import pytest

from backend.browser_agent import (
    MAX_RESULT_BYTES,
    BrowserAgent,
    BrowserAgentError,
    execute,
    read_page,
)

USER_ID = '11111111-1111-1111-1111-111111111111'

PUBLIC_IP = '93.184.216.34'
ADDRESSES = {
    'example.com': [PUBLIC_IP],
    'example.org': ['93.184.216.35'],
    'internal.example.com': ['192.168.1.20'],
    'mixed.example.com': [PUBLIC_IP, '10.0.0.8'],
}


def fake_resolver(hostname):
    return list(ADDRESSES.get(hostname, []))


PAGE_HTML = """<!doctype html>
<html>
<head>
<title>Example Page</title>
<style>body { color: red; }</style>
<script>var secret = 'script-text-must-not-appear';</script>
</head>
<body>
<nav>Home Products Pricing Sign in</nav>
<header>Site banner</header>
<main>
<h1>Welcome</h1>
<p>This is the readable body of the page.</p>
<p>Second paragraph with <b>bold</b> words.</p>
</main>
<footer>Copyright nobody</footer>
</body>
</html>
"""


def _handler(request):
    host = request.url.host
    path = request.url.path
    if host == 'example.com' and path == '/page':
        return httpx.Response(
            200, headers={'content-type': 'text/html; charset=utf-8'}, content=PAGE_HTML
        )
    if host == 'example.com' and path == '/plain':
        return httpx.Response(
            200,
            headers={'content-type': 'text/plain'},
            content=b'Plain text page.\nSecond line here.',
        )
    if host == 'example.com' and path == '/redirect':
        return httpx.Response(302, headers={'location': '/page'})
    if host == 'example.com' and path == '/chain':
        return httpx.Response(302, headers={'location': '/chain-two'})
    if host == 'example.com' and path == '/chain-two':
        return httpx.Response(301, headers={'location': 'https://example.org/page'})
    if host == 'example.org' and path == '/page':
        return httpx.Response(
            200,
            headers={'content-type': 'text/html'},
            content=b'<html><head><title>Other Host</title></head>'
            b'<body><p>Landed on the second host.</p></body></html>',
        )
    if host == 'example.com' and path == '/to-private':
        return httpx.Response(
            302, headers={'location': 'http://internal.example.com/secret'}
        )
    if host == 'internal.example.com' and path == '/secret':
        return httpx.Response(
            200, headers={'content-type': 'text/html'}, content=b'<p>secret</p>'
        )
    if host == 'example.com' and path == '/loop':
        return httpx.Response(302, headers={'location': '/loop'})
    if host == 'example.com' and path == '/big':
        return httpx.Response(
            200,
            headers={'content-type': 'text/plain'},
            content=b'x' * (2 * 1024 * 1024 + 1),
        )
    if host == 'example.com' and path == '/image':
        return httpx.Response(
            200, headers={'content-type': 'image/png'}, content=b'\x89PNG\r\n'
        )
    if host == 'example.com' and path == '/long':
        body = 'word ' * 8000
        html = (
            '<html><head><title>Long Page</title></head><body><p>'
            + body
            + '</p></body></html>'
        )
        return httpx.Response(
            200, headers={'content-type': 'text/html'}, content=html.encode()
        )
    if host == 'example.com' and path == '/missing':
        return httpx.Response(404, headers={'content-type': 'text/html'}, content=b'nope')
    return httpx.Response(
        404, headers={'content-type': 'text/html'}, content=b'not found'
    )


def _client():
    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


def _agent():
    return BrowserAgent(http_client=_client(), resolver=fake_resolver)


def test_public_page_success_extracts_title_and_text_without_scripts():
    page = asyncio.run(_agent().read_page(USER_ID, 'https://example.com/page'))
    assert page['finalUrl'] == 'https://example.com/page'
    assert page['title'] == 'Example Page'
    assert 'This is the readable body of the page.' in page['text']
    assert 'Second paragraph with bold words.' in page['text']
    assert 'script-text-must-not-appear' not in page['text']
    assert 'color: red' not in page['text']
    assert 'Home Products Pricing' not in page['text']
    assert 'Site banner' not in page['text']
    assert 'Copyright nobody' not in page['text']
    assert page['bytes'] == len(PAGE_HTML.encode('utf-8'))
    assert page['fetchedAt']


def test_plain_text_page_success_via_module_function():
    page = asyncio.run(
        read_page(
            USER_ID,
            'http://example.com/plain',
            http_client=_client(),
            resolver=fake_resolver,
        )
    )
    assert page['title'] == ''
    assert page['text'] == 'Plain text page. Second line here.'


def test_redirect_chain_success_follows_relative_and_cross_host_hops():
    page = asyncio.run(_agent().read_page(USER_ID, 'https://example.com/chain'))
    assert page['finalUrl'] == 'https://example.org/page'
    assert page['title'] == 'Other Host'
    assert 'Landed on the second host.' in page['text']

    single = asyncio.run(_agent().read_page(USER_ID, 'https://example.com/redirect'))
    assert single['finalUrl'] == 'https://example.com/page'
    assert single['title'] == 'Example Page'


def test_redirect_to_private_address_is_blocked():
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(_agent().read_page(USER_ID, 'https://example.com/to-private'))
    assert caught.value.code == 'BROWSER_URL_BLOCKED'


def test_direct_private_addresses_are_blocked():
    for url in (
        'http://192.168.0.5/admin',
        'http://10.0.0.1/',
        'http://127.0.0.1:8000/',
        'http://[::1]/',
        'http://internal.example.com/secret',
        'http://mixed.example.com/page',
    ):
        with pytest.raises(BrowserAgentError) as caught:
            asyncio.run(_agent().read_page(USER_ID, url))
        assert caught.value.code == 'BROWSER_URL_BLOCKED', url


def test_non_http_schemes_are_blocked():
    for url in (
        'file:///etc/passwd',
        'ftp://example.com/file',
        'javascript:alert(1)',
        'data:text/html,<p>hi</p>',
        'example.com/page',
    ):
        with pytest.raises(BrowserAgentError) as caught:
            asyncio.run(_agent().read_page(USER_ID, url))
        assert caught.value.code == 'BROWSER_URL_BLOCKED', url


def test_oversized_response_is_rejected():
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(_agent().read_page(USER_ID, 'https://example.com/big'))
    assert caught.value.code == 'BROWSER_TOO_LARGE'


def test_unsupported_content_type_is_rejected():
    with pytest.raises(BrowserAgentError) as caught:
        asyncio.run(_agent().read_page(USER_ID, 'https://example.com/image'))
    assert caught.value.code == 'BROWSER_UNSUPPORTED_TYPE'


def test_http_error_and_redirect_loop_fail_as_fetch_failed():
    with pytest.raises(BrowserAgentError) as missing:
        asyncio.run(_agent().read_page(USER_ID, 'https://example.com/missing'))
    assert missing.value.code == 'BROWSER_FETCH_FAILED'
    with pytest.raises(BrowserAgentError) as loop:
        asyncio.run(_agent().read_page(USER_ID, 'https://example.com/loop'))
    assert loop.value.code == 'BROWSER_FETCH_FAILED'


def test_extracted_text_is_truncated_at_the_cap():
    page = asyncio.run(_agent().read_page(USER_ID, 'https://example.com/long'))
    assert len(page['text']) == 20000


def test_execute_returns_summary_and_text_within_the_ledger_fence():
    result = asyncio.run(
        execute(
            'browser.read',
            USER_ID,
            {'url': 'https://example.com/page'},
            http_client=_client(),
            resolver=fake_resolver,
        )
    )
    assert result['summary']['finalUrl'] == 'https://example.com/page'
    assert result['summary']['title'] == 'Example Page'
    assert 'readable body of the page' in result['text']
    assert result['truncated'] is False
    assert len(json.dumps(result).encode('utf-8')) <= MAX_RESULT_BYTES


def test_execute_truncates_long_text_and_flags_it():
    result = asyncio.run(
        _agent().execute(
            'browser.read', USER_ID, {'url': 'https://example.com/long'}
        )
    )
    assert result['truncated'] is True
    assert result['summary']['truncated'] is True
    assert result['textLength'] == 20000
    assert len(result['text']) < result['textLength']
    assert len(json.dumps(result).encode('utf-8')) <= MAX_RESULT_BYTES


def test_execute_rejects_unknown_capability_and_bad_payloads():
    with pytest.raises(BrowserAgentError) as unknown:
        asyncio.run(_agent().execute('browser.act', USER_ID, {'url': 'https://example.com/page'}))
    assert unknown.value.code == 'CAPABILITY_NOT_FOUND'
    with pytest.raises(BrowserAgentError) as missing:
        asyncio.run(_agent().execute('browser.read', USER_ID, {}))
    assert missing.value.code == 'INVALID_RUN_INPUT'
    with pytest.raises(BrowserAgentError) as wrong_type:
        asyncio.run(_agent().execute('browser.read', USER_ID, {'url': 42}))
    assert wrong_type.value.code == 'INVALID_RUN_INPUT'


def test_async_resolver_is_supported():
    async def async_resolver(hostname):
        return fake_resolver(hostname)

    agent = BrowserAgent(http_client=_client(), resolver=async_resolver)
    page = asyncio.run(agent.read_page(USER_ID, 'https://example.com/page'))
    assert page['title'] == 'Example Page'
