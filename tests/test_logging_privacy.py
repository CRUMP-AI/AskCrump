import logging

from backend.application import configure_logging


def test_upstream_http_request_urls_are_not_emitted_at_info_level():
    httpx_logger = logging.getLogger('httpx')
    httpcore_logger = logging.getLogger('httpcore')
    previous_httpx = httpx_logger.level
    previous_httpcore = httpcore_logger.level
    try:
        httpx_logger.setLevel(logging.INFO)
        httpcore_logger.setLevel(logging.DEBUG)
        configure_logging()

        assert httpx_logger.level == logging.WARNING
        assert httpcore_logger.level == logging.WARNING
    finally:
        httpx_logger.setLevel(previous_httpx)
        httpcore_logger.setLevel(previous_httpcore)
