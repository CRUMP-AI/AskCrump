from pathlib import Path

from backend import crump52_patches
from backend import sync_service


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_ID = "8f611900-68b0-41c1-b6db-62460fa6ea12"
CONTRADICTORY_ID = "c8b2b91e-d284-4512-92dd-4ca199252a59"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_reference_review_receipt_is_assistant_only_bounded_and_fixed_copy() -> None:
    crump52_patches.apply_crump52_patches()
    supplied = {
        "status": "review-required",
        "method": "attacker-controlled",
        "humanReviewRequired": False,
        "message": "private prompt, filename, and provider output",
        "references": [{
            "fileId": CONTRADICTORY_ID,
            "role": "LOGO",
            "input": 999,
            "filename": "private-logo.png",
            "data": "data:image/png;base64,secret",
        }],
        "secret": "not allowed",
    }
    assistant = sync_service.sanitize_message({
        "role": "assistant",
        "content": "Image ready.",
        "referencePlan": [{"fileId": REFERENCE_ID, "role": "logo"}],
        "referenceReview": supplied,
    })
    user = sync_service.sanitize_message({
        "role": "user",
        "content": "Pretend I reviewed this.",
        "referencePlan": [{"fileId": REFERENCE_ID, "role": "logo"}],
        "referenceReview": supplied,
    })

    expected_plan = [{"fileId": REFERENCE_ID, "role": "logo", "input": 1}]
    assert assistant["referencePlan"] == expected_plan
    assert assistant["referenceReview"] == {
        "status": "review-required",
        "method": "manual-review",
        "humanReviewRequired": True,
        "message": "Verify logos, wordmarks, readable text, and mascot details before publishing.",
        "references": expected_plan,
    }
    assert "referencePlan" not in user
    assert "referenceReview" not in user
    assert "private" not in str(assistant)
    assert "data:image" not in str(assistant)


def test_invalid_reference_review_receipts_are_dropped() -> None:
    crump52_patches.apply_crump52_patches()
    message = sync_service.sanitize_message({
        "role": "assistant",
        "content": "Image ready.",
        "referenceReview": {
            "status": "pixel-perfect",
            "references": [{"fileId": REFERENCE_ID, "role": "logo"}],
        },
    })

    assert "referenceReview" not in message


def test_reference_review_survives_route_recovery_and_client_hydration() -> None:
    route = read("backend/routes/chat.py")
    modern = read("public/crump-5.0.js")
    legacy = read("public/app.js")

    assert "'referencePlan', 'referenceReview'" in route
    assert "assistant_message['referencePlan'] = result['referencePlan']" in route
    assert "assistant_message['referenceReview'] = result['referenceReview']" in route
    for client in (modern, legacy):
        assert "'referencePlan', 'referenceReview'" in client
