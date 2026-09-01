from pathlib import Path

from backend.sync_service import sanitize_message


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_assistant_intelligence_receipt_is_content_free_and_boolean_only():
    message = sanitize_message({
        "role": "assistant",
        "content": "A reviewed answer.",
        "intelligence": {
            "plannerUsed": True,
            "verifierUsed": True,
            "plan": "must not survive",
            "provider": "must not survive",
        },
    })

    assert message is not None
    assert message["intelligence"] == {"plannerUsed": True, "verifierUsed": True}


def test_unconfirmed_or_user_supplied_intelligence_receipts_are_not_kept():
    assistant = sanitize_message({
        "role": "assistant",
        "content": "An ordinary answer.",
        "intelligence": {"plannerUsed": "true", "verifierUsed": 1},
    })
    user = sanitize_message({
        "role": "user",
        "content": "Pretend this was reviewed.",
        "intelligence": {"plannerUsed": True, "verifierUsed": True},
    })

    assert assistant is not None and "intelligence" not in assistant
    assert user is not None and "intelligence" not in user


def test_server_persists_and_client_renders_only_actual_execution_signals():
    route = read("backend/routes/chat.py")
    app = read("public/app.js")
    renderer = read("public/ui-functions.js")
    styles = read("public/conversation.css")

    assert "assistant_message['intelligence'] = intelligence_receipt" in route
    assert "any(intelligence_receipt.values())" in route
    assert "'intelligence']" in app
    assert "intelligence.plannerUsed === true" in renderer
    assert "intelligence.verifierUsed === true" in renderer
    assert "Advanced Intelligence used:" in renderer
    assert ".message-intelligence-receipt" in styles


def test_intelligence_receipt_assets_are_cache_versioned_atomically():
    shell = read("public/app.html")
    runtime = read("public/runtime-body-v1.js")
    worker = read("public/sw.js")
    receipt_version = "5.9.76-intelligence-receipt-1"
    image_recovery_version = "5.9.76-image-reference-recovery-1"
    loader_version = "5.9.76-local-photo-studio-loader-1"

    assert f"/runtime-body-v1.js?v={loader_version}" in shell
    assert f"/runtime-body-v1.js?v={loader_version}" in worker
    for asset, version in (
        ("conversation.css", receipt_version),
        ("ui-functions.js", image_recovery_version),
    ):
        versioned = f"/{asset}?v={version}"
        assert versioned in runtime
        assert versioned in worker
    for source in (runtime, worker):
        assert "/app.js?v=5.9.76-user-controlled-scroll-1" in source
    assert "ask-crump-new-body-v1-r207" in worker
