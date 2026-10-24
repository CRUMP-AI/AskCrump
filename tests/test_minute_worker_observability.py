from __future__ import annotations

import json
import logging

from backend.minute_worker_observability import (
    log_email_queue_outcome,
    log_minute_worker_turn,
)


class ExplosiveValue:
    def __str__(self):
        raise AssertionError('private values must not be stringified')

    def __int__(self):
        raise AssertionError('private values must not be coerced')


class RaisingHandler(logging.Handler):
    def emit(self, record):
        raise RuntimeError('sink unavailable')


def test_email_queue_outcome_is_allowlisted_and_bounded(caplog):
    logger = logging.getLogger('test.minute_worker_observability')
    caplog.set_level(logging.INFO, logger=logger.name)

    record = log_email_queue_outcome(
        logger,
        lane='private-user@example.test',
        handled=True,
        status='private-token-fixture',
        attempt=99,
        provider_attempts=4,
    )

    assert record == {
        'component': 'minute_worker',
        'event': 'email_queue_outcome',
        'lane': 'unknown',
        'handled': True,
        'status': 'unknown',
    }
    assert json.loads(caplog.records[-1].message) == record
    assert 'private-user' not in caplog.text
    assert 'private-token-fixture' not in caplog.text


def test_email_queue_outcome_does_not_coerce_unknown_values(caplog):
    logger = logging.getLogger('test.minute_worker_observability')
    caplog.set_level(logging.INFO, logger=logger.name)

    record = log_email_queue_outcome(
        logger,
        lane='verification-email',
        handled=False,
        status=ExplosiveValue(),
        attempt=ExplosiveValue(),
        provider_attempts='1',
    )

    assert record == {
        'component': 'minute_worker',
        'event': 'email_queue_outcome',
        'lane': 'verification-email',
        'handled': False,
        'status': 'unknown',
    }
    assert json.loads(caplog.records[-1].message) == record


def test_logging_sink_failure_does_not_escape_observability_helpers():
    logger = logging.Logger('test.minute_worker_observability.raising', logging.INFO)
    logger.addHandler(RaisingHandler())

    queue_record = log_email_queue_outcome(
        logger,
        lane='verification-email',
        handled=False,
        status='idle',
    )
    turn_record = log_minute_worker_turn(
        logger,
        logging.WARNING,
        result='retryable_database_503',
        worker='idle',
        handled=False,
        status='none',
        lane_outcomes={'verification-email': 'claim_database_error'},
        degraded_lanes=('verification-email',),
    )

    assert queue_record['status'] == 'idle'
    assert turn_record['result'] == 'retryable_database_503'


def test_turn_outcome_rebuilds_only_fixed_lanes_and_categories(caplog):
    logger = logging.getLogger('test.minute_worker_observability')
    caplog.set_level(logging.INFO, logger=logger.name)

    record = log_minute_worker_turn(
        logger,
        logging.INFO,
        result='handled',
        worker='password-reset-email',
        handled=True,
        status='provider_accepted',
        lane_outcomes={
            'verification-email': 'claim_database_error',
            'password-reset-email': 'handled',
            'private-account-id': 'private-message',
            'code': 'private-output',
        },
        degraded_lanes=('verification-email', 'private-account-id'),
    )

    assert record == {
        'component': 'minute_worker',
        'event': 'turn_outcome',
        'result': 'handled',
        'worker': 'password-reset-email',
        'handled': True,
        'status': 'provider_accepted',
        'lane_outcomes': {
            'verification-email': 'claim_database_error',
            'password-reset-email': 'handled',
        },
        'degraded_lanes': ['verification-email'],
        'degraded_lane_count': 1,
    }
    assert json.loads(caplog.records[-1].message) == record
    assert 'private-account-id' not in caplog.text
    assert 'private-message' not in caplog.text
    assert 'private-output' not in caplog.text
