from datetime import datetime, timedelta, timezone

import pytest

from backend.sync_service import (
    parse_datetime,
    push_sync,
    safe_client_time,
    sanitize_message,
    sanitize_settings,
)


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.settings = None

    async def rpc(self, function_name, payload):
        assert function_name == 'apply_chat_sync'
        chat_id = payload['p_chat_id']
        existing = self.rows.get(chat_id)
        incoming_time = parse_datetime(payload['p_updated_at'])
        incoming_revision = int(payload['p_revision'])
        if existing:
            server_time = parse_datetime(existing['updated_at'])
            server_revision = int(existing['revision'])
            if incoming_time < server_time or (incoming_time == server_time and incoming_revision <= server_revision):
                return [{'accepted': False, 'resulting_revision': server_revision}]
            incoming_revision = max(incoming_revision, server_revision + 1)
        self.rows[chat_id] = {
            'chat_id': chat_id,
            'title': payload['p_title'],
            'messages': payload['p_messages'],
            'created_at': payload['p_created_at'],
            'updated_at': payload['p_updated_at'],
            'deleted_at': payload['p_deleted_at'],
            'revision': incoming_revision,
        }
        return [{'accepted': True, 'resulting_revision': incoming_revision}]

    async def upsert(self, table, payload, *, on_conflict):
        assert table == 'user_settings'
        self.settings = dict(payload)
        return [payload]


def test_client_time_is_clamped():
    future = datetime.now(timezone.utc) + timedelta(days=30)
    result = parse_datetime(safe_client_time(future.isoformat()))
    assert result <= datetime.now(timezone.utc) + timedelta(seconds=2)


def test_message_and_setting_sanitization():
    message = sanitize_message({
        'role': 'assistant',
        'content': 'hello\x00 world',
        'imageUrl': 'javascript:alert(1)',
        'files': [{'name': 'report.pdf', 'type': 'application/pdf'}],
    })
    assert message['content'] == 'hello world'
    assert 'imageUrl' not in message
    assert message['files'][0]['name'] == 'report.pdf'

    settings = sanitize_settings({
        'assistant_name': '  Crump  ',
        'work_mode': 1,
        'work_start': 99,
        'unknown': 'discard me',
    })
    assert settings == {
        'assistant_name': 'Crump',
        'work_mode': True,
        'work_start': 23,
    }


@pytest.mark.asyncio
async def test_newer_chat_wins_and_older_chat_is_ignored():
    db = FakeDB()
    chat_id = '7be94047-aaf4-458a-a599-8f37a0256e52'
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    new = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    first = await push_sync(db, 'user-1', {'chats': [{
        'id': chat_id,
        'title': 'Newer',
        'updatedAt': new,
        'createdAt': old,
        'revision': 2,
        'messages': [{'role': 'user', 'content': 'latest'}],
    }]})
    assert first['accepted'] == [chat_id]

    second = await push_sync(db, 'user-1', {'chats': [{
        'id': chat_id,
        'title': 'Older',
        'updatedAt': old,
        'createdAt': old,
        'revision': 1,
        'messages': [{'role': 'user', 'content': 'stale'}],
    }]})
    assert second['ignored'] == [chat_id]
    assert db.rows[chat_id]['title'] == 'Newer'


def test_presence_and_check_in_metadata_survive_sanitization():
    user_message = sanitize_message({
        'id': '8f611900-68b0-41c1-b6db-62460fa6ea12',
        'role': 'user',
        'content': 'Did you finish the application?',
        'deliveryStatus': 'seen',
        'replyStatus': 'replied',
        'deliveryUpdatedAt': '2026-08-01T12:00:00+00:00',
        'deliveredAt': '2026-08-01T12:00:01+00:00',
        'seenAt': '2026-08-01T12:00:02+00:00',
        'inReplyTo': 'd725d9f2-0e90-42d7-a42e-5a19f8dfa2a8',
        'replyError': 'ignored client text',
        'unknown': 'discard',
    })
    assert user_message['deliveryStatus'] == 'seen'
    assert user_message['replyStatus'] == 'replied'
    assert user_message['inReplyTo'] == 'd725d9f2-0e90-42d7-a42e-5a19f8dfa2a8'
    assert 'unknown' not in user_message

    assistant_message = sanitize_message({
        'id': 'fdb28f7f-39b9-43ad-ae2d-a804ec0641a8',
        'role': 'assistant',
        'content': 'How did the application go?',
        'checkInId': '1c6f0e61-847a-44e8-a72a-e3dbf9668edc',
        'origin': 'check_in',
    })
    assert assistant_message['origin'] == 'check_in'
    assert assistant_message['checkInId'] == '1c6f0e61-847a-44e8-a72a-e3dbf9668edc'


def test_resume_purpose_survives_sync_without_accepting_arbitrary_values():
    resume = sanitize_message({
        'id': '8f611900-68b0-41c1-b6db-62460fa6ea12',
        'role': 'user',
        'content': 'Led fraud operations for five years.',
        'requestMeta': {'artifactFormat': 'docx', 'artifactPurpose': 'RESUME'},
    })
    invalid = sanitize_message({
        'id': 'c8b2b91e-d284-4512-92dd-4ca199252a59',
        'role': 'user',
        'content': 'Create a document.',
        'requestMeta': {'artifactFormat': 'docx', 'artifactPurpose': 'private-freeform-purpose'},
    })
    assert resume['requestMeta']['artifactPurpose'] == 'resume'
    assert 'artifactPurpose' not in invalid['requestMeta']


def test_manuscript_workspace_handoff_survives_cross_device_sanitization():
    message = sanitize_message({
        'id': 'c8b2b91e-d284-4512-92dd-4ca199252a59',
        'role': 'assistant',
        'content': 'Your manuscript workspace is ready.',
        'manuscriptWorkspace': {
            'projectId': '1c6f0e61-847a-44e8-a72a-e3dbf9668edc',
            'manuscriptId': '8f611900-68b0-41c1-b6db-62460fa6ea12',
            'title': 'Northbound',
            'chapterCount': 28,
            'targetWords': 80000,
            'preferredExportFormat': 'docx',
            'untrusted': 'discard',
        },
    })
    workspace = message['manuscriptWorkspace']
    assert workspace['title'] == 'Northbound'
    assert workspace['chapterCount'] == 28
    assert workspace['targetWords'] == 80000
    assert 'untrusted' not in workspace
