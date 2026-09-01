import httpx
import pytest

from backend.media_service import MediaService


def test_image_request_detection():
    assert MediaService.is_image_request('Create an image of a quiet city at night')
    assert MediaService.is_image_request('anything', 'image')
    assert not MediaService.is_image_request('What is in this image?')


def test_edit_request_requires_image_reference():
    image = [{'mime_type': 'image/jpeg'}]
    pdf = [{'mime_type': 'application/pdf'}]
    assert MediaService.is_edit_request('Remove the background', image)
    assert not MediaService.is_edit_request('Remove the background', pdf)


def test_balanced_image_quality_is_the_default():
    assert MediaService._image_settings({}) == ('1024x1024', 'medium', 'png')
    assert MediaService._image_settings({'imageQuality': 'high'})[1] == 'high'


@pytest.mark.asyncio
async def test_image_request_retries_one_transient_provider_failure(monkeypatch, caplog):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            503 if calls == 1 else 200,
            request=request,
            headers={'x-request-id': 'unique-transient-request'},
            json={'data': []},
        )

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr('backend.media_service.asyncio.sleep', no_delay)
    with caplog.at_level('WARNING', logger='askcrump.media'):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await MediaService._post_image_request(client, 'https://api.openai.com/v1/images/generations')

    assert response.status_code == 200
    assert calls == 2
    assert [record.getMessage() for record in caplog.records] == [
        'Image provider transient response retry status=503 attempt=1'
    ]
    assert 'unique-transient-request' not in caplog.text


@pytest.mark.asyncio
async def test_image_request_does_not_retry_permanent_rejection(monkeypatch):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, request=request, json={'error': {'code': 'bad_request'}})

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr('backend.media_service.asyncio.sleep', no_delay)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await MediaService._post_image_request(client, 'https://api.openai.com/v1/images/generations')

    assert response.status_code == 400
    assert calls == 1
