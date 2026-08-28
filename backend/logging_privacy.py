"""Logging boundaries that prevent dependency transports from exposing private URLs."""

from __future__ import annotations

import logging


_TRANSPORT_LOGGER_PREFIXES = ("httpx", "httpcore")


def _is_transport_record(record: logging.LogRecord) -> bool:
    name = str(record.name or "")
    return any(
        name == prefix or name.startswith(f"{prefix}.")
        for prefix in _TRANSPORT_LOGGER_PREFIXES
    )


class TransportPrivacyFilter(logging.Filter):
    """Drop URL-bearing dependency records before any configured handler emits them."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not _is_transport_record(record)


_transport_privacy_filter = TransportPrivacyFilter()


def enforce_transport_log_privacy() -> None:
    """Apply the transport boundary after host logging configuration and before requests."""

    root = logging.getLogger()
    candidate_loggers: list[logging.Logger] = [
        logging.getLogger(prefix) for prefix in _TRANSPORT_LOGGER_PREFIXES
    ]
    for name, value in logging.Logger.manager.loggerDict.items():
        if not isinstance(value, logging.Logger):
            continue
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _TRANSPORT_LOGGER_PREFIXES):
            candidate_loggers.append(value)

    handlers = list(root.handlers)
    for transport_logger in candidate_loggers:
        transport_logger.setLevel(logging.WARNING)
        if _transport_privacy_filter not in transport_logger.filters:
            transport_logger.addFilter(_transport_privacy_filter)
        handlers.extend(transport_logger.handlers)

    for handler in handlers:
        if _transport_privacy_filter not in handler.filters:
            handler.addFilter(_transport_privacy_filter)
