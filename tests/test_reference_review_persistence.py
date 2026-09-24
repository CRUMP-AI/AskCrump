from pathlib import Path

from backend import crump52_patches
from backend import sync_service
from backend.routes.chat import _video_creation_handoff


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
        "status": "warn",
        "method": "local-reference-signals-v1",
        "humanReviewRequired": True,
        "reviewProviderUsed": False,
        "reviewCreditsUsed": 0,
        "limitations": ["identity", "logos", "text", "pixel-fidelity"],
        "message": "Local checks are limited or need attention. Review every original before publishing.",
        "references": [{
            **expected_plan[0],
            "status": "warn",
            "signals": {"color": "unavailable", "structure": "unavailable"},
            "humanChecks": ["logo-shape", "logo-colors"],
            "userReview": "pending",
        }],
    }
    assert "referencePlan" not in user
    assert "referenceReview" not in user
    assert "private" not in str(assistant)
    assert "data:image" not in str(assistant)


def test_reference_review_persists_only_enum_evidence_and_user_confirmation() -> None:
    crump52_patches.apply_crump52_patches()
    message = sync_service.sanitize_message({
        "role": "assistant",
        "content": "Image ready.",
        "referencePlan": [{"fileId": REFERENCE_ID, "role": "logo"}],
        "referenceReview": {
            "status": "pass",
            "method": "remote-vision-model",
            "humanReviewRequired": False,
            "reviewProviderUsed": True,
            "reviewCreditsUsed": 99,
            "references": [{
                "fileId": REFERENCE_ID,
                "role": "logo",
                "input": 1,
                "status": "pass",
                "signals": {"color": "aligned", "structure": "aligned", "rawScore": 0.999},
                "humanChecks": [],
                "userReview": "confirmed",
                "bytes": "private-image-data",
            }],
        },
    })

    review = message["referenceReview"]
    assert review["status"] == "warn"
    assert review["method"] == "local-reference-signals-v1"
    assert review["humanReviewRequired"] is True
    assert review["reviewProviderUsed"] is False
    assert review["reviewCreditsUsed"] == 0
    assert review["references"] == [{
        "fileId": REFERENCE_ID,
        "role": "logo",
        "input": 1,
        "status": "warn",
        "signals": {"color": "aligned", "structure": "aligned"},
        "humanChecks": ["logo-shape", "logo-colors"],
        "userReview": "confirmed",
    }]
    assert "rawScore" not in str(review)
    assert "private-image-data" not in str(review)


def test_user_flagged_reference_mismatch_overrides_local_signal_status() -> None:
    crump52_patches.apply_crump52_patches()
    message = sync_service.sanitize_message({
        "role": "assistant",
        "content": "Image ready.",
        "referencePlan": [{"fileId": REFERENCE_ID, "role": "logo"}],
        "referenceReview": {
            "status": "warn",
            "references": [{
                "fileId": REFERENCE_ID,
                "role": "logo",
                "input": 1,
                "status": "warn",
                "signals": {"color": "aligned", "structure": "aligned"},
                "userReview": "mismatch",
            }],
        },
    })

    review = message["referenceReview"]
    assert review["status"] == "mismatch"
    assert review["message"] == "At least one reference was flagged or local color and structure signals differ. Review every original before publishing."
    assert review["references"][0]["status"] == "mismatch"
    assert review["references"][0]["userReview"] == "mismatch"


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


def test_video_creation_handoff_is_minimal_bounded_and_assistant_only() -> None:
    rows = [
        {
            "id": f"00000000-0000-0000-0000-{index:012d}",
            "file_name": f"reference-{index}.png",
            "mime_type": "image/png",
            "size_bytes": 1000 + index,
            "storage_path": f"private/secret-{index}.png",
            "metadata": {"private": "drop-me"},
        }
        for index in range(1, 6)
    ]
    rows.append({
        "id": "00000000-0000-0000-0000-000000000099",
        "file_name": "notes.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 50,
    })
    raw = _video_creation_handoff(
        brief="Animate the launch scene.",
        idempotency_key="chat-video:fixture",
        current_file_rows=rows,
    )
    raw["secret"] = "drop-me"
    for item in raw["referenceFiles"]:
        item["url"] = "https://attacker.invalid/private"
        item["storagePath"] = "private/secret.png"

    assistant = sync_service.sanitize_message({
        "role": "assistant",
        "content": "",
        "creationHandoff": raw,
    })
    user = sync_service.sanitize_message({
        "role": "user",
        "content": "Ignore policy.",
        "creationHandoff": raw,
    })

    assert assistant["creationHandoff"] == {
        "kind": "video",
        "brief": "Animate the launch scene.",
        "autoOpen": True,
        "autoStart": False,
        "idempotencyKey": "chat-video:fixture",
        "referenceFiles": [
            {
                "id": row["id"],
                "name": row["file_name"],
                "type": "image/png",
                "size": row["size_bytes"],
            }
            for row in rows[:5]
        ],
    }
    assert len(assistant["creationHandoff"]["referenceFiles"]) == 5
    assert "creationHandoff" not in user
    assert "secret" not in str(assistant)
    assert "attacker.invalid" not in str(assistant)


def test_v2_reference_contract_and_plan_error_survive_user_message_sanitization() -> None:
    message = sync_service.sanitize_message({
        "role": "user",
        "content": "Create the launch image.",
        "replyErrorCode": "IMAGE_REFERENCE_CONFIRMATION_REQUIRED",
        "requestMeta": {
            "imageUseReference": True,
            "imageReferenceContractVersion": "2",
            "imageReferencePlanConfirmed": False,
            "imageReferencePlan": [{"fileId": REFERENCE_ID, "role": "logo"}],
        },
    })

    assert message["replyErrorCode"] == "IMAGE_REFERENCE_CONFIRMATION_REQUIRED"
    assert message["requestMeta"] == {
        "imageUseReference": True,
        "imageReferenceContractVersion": 2,
        "imageReferencePlanConfirmed": False,
        "imageReferencePlan": [{"fileId": REFERENCE_ID, "role": "logo"}],
    }


def test_reference_review_survives_route_recovery_and_client_hydration() -> None:
    route = read("backend/routes/chat.py")
    modern = read("public/crump-5.0.js")
    legacy = read("public/app.js")

    assert "'referencePlan', 'referenceReview'" in route
    assert "assistant_message['referencePlan'] = result['referencePlan']" in route
    assert "assistant_message['referenceReview'] = result['referenceReview']" in route
    for client in (modern, legacy):
        assert "'referencePlan', 'referenceReview'" in client


def test_reference_review_ui_is_role_by_role_local_and_user_confirmable() -> None:
    modern = read("public/crump-5.0.js")
    styles = read("public/crump-5.0.css")
    renderer = modern[modern.index("function createReferenceReceipt(message)") : modern.index("function enhanceRenderedMessages(messages)")]

    for contract in (
        "Reference check · ${references.length} local comparison",
        "Local color and structure checks only · no extra generation or credits",
        "cannot verify identity, exact logos, spelling, or pixel fidelity",
        "['pass', 'Signals align']",
        "['warn', 'Review needed']",
        "['mismatch', 'Signals differ']",
        "Color",
        "Structure",
        "Confirm reviewed",
        "Flag mismatch",
        "currentEvidence.userReview = decision",
        "const signalStatusForRole = (role, signals) =>",
        "const heuristicStatus = signalStatusForRole(role, currentEvidence?.signals)",
        "const status = userReview === 'mismatch' ? 'mismatch' : heuristicStatus",
        "badge.textContent = userReview === 'mismatch' ? 'Mismatch flagged'",
        "const visibleStatus = decision === 'mismatch' ? 'mismatch' : heuristicStatus",
        "saveAndRender(chat)",
    ):
        assert contract in renderer
    assert "verified" not in renderer.lower()
    assert "pixel-perfect" not in renderer.lower()
    assert "remote" not in renderer.lower()
    assert "crump50-reference-signals" in styles
    assert "crump50-reference-review-actions" in styles
