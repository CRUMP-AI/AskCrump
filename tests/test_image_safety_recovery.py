from backend.routes.chat import _ai_error_recovery


def test_correctable_image_rejections_receive_a_bounded_recovery_receipt() -> None:
    for code in ("IMAGE_SAFETY_REJECTED", "IMAGE_PROVIDER_REJECTED"):
        assert _ai_error_recovery(code) == {
            "action": "revise_image_request",
            "usageRestored": True,
            "changeRequired": "prompt_or_reference",
        }
    for code in ("INVALID_IMAGE_EDIT_SOURCE", "IMAGE_EDIT_SOURCE_TOO_LARGE"):
        assert _ai_error_recovery(code) == {
            "action": "revise_image_request",
            "usageRestored": True,
            "changeRequired": "reference",
        }
    for code in (
        "IMAGE_ORGANIZATION_VERIFICATION_REQUIRED",
        "IMAGE_PROVIDER_AUTH_ERROR",
        "IMAGE_PROVIDER_BILLING_REQUIRED",
        "IMAGE_RATE_LIMIT",
        "IMAGE_UPSTREAM_ERROR",
        "AI_SERVICE_ERROR",
        "",
    ):
        assert _ai_error_recovery(code) is None
