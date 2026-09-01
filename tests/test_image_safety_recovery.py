from backend.routes.chat import _ai_error_recovery


def test_only_image_safety_rejections_receive_the_static_recovery_receipt() -> None:
    assert _ai_error_recovery("IMAGE_SAFETY_REJECTED") == {
        "action": "revise_image_request",
        "usageRestored": True,
    }
    for code in ("IMAGE_RATE_LIMIT", "IMAGE_PROVIDER_REJECTED", "AI_SERVICE_ERROR", ""):
        assert _ai_error_recovery(code) is None
