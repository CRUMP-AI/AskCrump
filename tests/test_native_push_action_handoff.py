import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_native_push_action_queue_is_wired_before_the_consumer_peek() -> None:
    native_entry = read("public/native-entry.js")
    presence = read("public/presence-manager.js")
    package = json.loads(read("package.json"))

    assert "createNativePushActionQueue" in native_entry
    assert "peekPendingPushActions: () => pushActionQueue.peek()" in native_entry
    assert "acknowledgePushAction: queueId => pushActionQueue.acknowledge(queueId)" in native_entry
    assert "pushActionQueue.retain(action)" in native_entry
    assert "if (retainedAction)" in native_entry

    listener = "window.addEventListener('crump:push-action', () => { void consumeAllPushActions(); });"
    peek = "window.CrumpNative?.peekPendingPushActions?.()"
    assert listener in presence
    assert peek in presence
    startup = "if (pushConsumerReady) queueMicrotask(startPushConsumer);"
    assert startup in presence
    assert presence.index(listener) < presence.index(startup)
    assert "handledPushActionIds.has(queueId)" in presence
    assert "inFlightPushActionIds.has(queueId)" in presence
    assert "const consumed = await openNotification(action)" in presence
    consumed = presence.index("const consumed = await openNotification(action)")
    assert consumed < presence.index("acknowledgePushAction?.(queueId)", consumed)
    assert "result?.success !== true || result?.deferred" in presence
    assert "This conversation is no longer available." in presence

    assert package["scripts"]["test:native-push-handoff"] == (
        "node scripts/verify-native-push-action-handoff.mjs"
    )
    assert "npm run test:native-push-handoff" in package["scripts"]["test"]


def test_native_push_action_ordering_fixture_executes() -> None:
    node = os.environ.get("ASKCRUMP_NODE_EXECUTABLE") or shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute the native push handoff fixture.")

    result = subprocess.run(
        [node, "scripts/verify-native-push-action-handoff.mjs"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "durable retry, reload, ordering, and deduplication all pass" in result.stdout


def test_native_push_queue_persists_only_navigation_data_until_acknowledged() -> None:
    queue = read("scripts/native-push-action-queue.mjs")

    assert "globalThis.sessionStorage" in queue
    assert "safeNavigationData" in queue
    assert "['chatId', 'chat_id', 'checkInId', 'check_in_id']" in queue
    assert "check-in:${checkInId}|action:${actionId}" in queue
    assert "DEFAULT_FALLBACK_DEDUP_WINDOW_MS" in queue
    assert "recentNavigation" in queue
    assert "notification.title" not in queue
    assert "notification.body" not in queue
    assert "function peek()" in queue
    assert "function acknowledge(queueId)" in queue
    assert "acknowledged.includes(dedupKey)" in queue


def test_native_push_consumer_and_runtime_loader_are_cache_busted_together() -> None:
    shell = read("public/app.html")
    worker = read("public/sw.js")
    runtime = read("public/runtime-body-v1.js")
    checker = read("scripts/check-javascript.mjs")

    runtime_url = "/runtime-body-v1.js?v=5.9.76-library-media-privacy-1"
    presence_url = "/presence-manager.js?v=5.9.76-native-push-handoff-1"
    cache_name = "ask-crump-new-body-v1-r266-library-media-privacy-1"
    assert runtime_url in shell
    assert runtime_url in worker
    assert presence_url in runtime
    assert presence_url in worker
    assert cache_name in worker
    assert cache_name in checker
    assert "const runtimeBodyVersion = manuscriptExportDeliveryVersion;" in checker
