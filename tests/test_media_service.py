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
