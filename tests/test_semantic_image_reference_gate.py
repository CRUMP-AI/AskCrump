from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend.intelligence_service import PreparedRequest
from backend.media_service import MediaService
from backend.routes import chat as chat_routes


CLIENT = TestClient(app_module.app)
ROOT = Path(__file__).resolve().parents[1]
IMAGE_ROWS = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "mime_type": "image/png",
        "file_name": "base.png",
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "mime_type": "image/png",
        "file_name": "logo.png",
    },
]


class GateDB:
    async def select_one(self, table, **_kwargs):
        if table == "user_settings":
            return {"assistant_name": "Crump", "work_mode": True}
        return None


class GateFeatures:
    def __init__(self) -> None:
        self.authorize = AsyncMock(
            return_value=SimpleNamespace(
                action_key="reference-gate-test",
                max_by_code={},
            )
        )
        self.consume_message = AsyncMock(
            return_value={
                "eventId": "message-usage",
                "used": 1,
                "limit": 100,
                "remaining": 99,
                "creditsSpent": 0,
            }
        )
        self.consume = AsyncMock(return_value={"eventId": "feature-usage", "creditsSpent": 0})
        self.refund = AsyncMock(return_value=None)

    @staticmethod
    def entitled(*_args):
        return False

    @staticmethod
    async def require_tier(*_args):
        return None

    @staticmethod
    def project_limit(_user):
        return 2


class GateMedia:
    def __init__(self, *, use_history: bool = False) -> None:
        self.use_history = use_history
        self.settings = SimpleNamespace(openai_image_model="test-image-model")
        self.plan = Mock(wraps=MediaService._image_reference_plan)
        self.understand = AsyncMock(
            return_value={"response": "I analyzed the attached images.", "model": "test-vision-model"}
        )
        self.generate_or_edit_image = AsyncMock(side_effect=self._generate)

    def needs_prior_files(self, _message):
        return self.use_history

    @staticmethod
    def is_image_request(message, creative_tool=None):
        return creative_tool == "image" or str(message).lower().startswith("generate a promo image")

    @staticmethod
    def is_edit_request(message, file_rows):
        return bool(file_rows) and str(message).lower().startswith("change that")

    @staticmethod
    def has_visual_files(file_rows):
        return any(str(row.get("mime_type") or "").startswith("image/") for row in file_rows)

    @staticmethod
    async def extract_nonvisual(_file_rows, **_kwargs):
        return ""

    @staticmethod
    async def legacy_inline_files(_file_rows):
        return []

    def _image_reference_plan(self, payload, image_rows):
        return self.plan(payload, image_rows)

    async def _generate(self, *, payload, file_rows, **_kwargs):
        plan = MediaService._image_reference_plan(payload, file_rows)
        return {
            "response": "I created the image with the confirmed references.",
            "model": self.settings.openai_image_model,
            "referencePlan": [
                {"fileId": item["fileId"], "role": item["role"], "input": index}
                for index, item in enumerate(plan, start=1)
            ],
        }


def _install_route_doubles(monkeypatch, creation_intent, *, historical: bool = False):
    media = GateMedia(use_history=historical)
    features = GateFeatures()

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={
                "id": "reference-user",
                "email": "owner@example.com",
                "full_name": "Owner",
                "subscription_tier": "free",
            },
            session={"id": "reference-session"},
            token="test-token",
        )

    async def prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload),
            requested_mode="auto",
            effective_mode="balanced",
            verification_level="off",
            route="chat",
            creation_intent=creation_intent,
            user_tier="free",
        )

    intelligence = SimpleNamespace(
        prepare=AsyncMock(side_effect=prepare),
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs["result"], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    resolved_rows = [dict(row) for row in IMAGE_ROWS]
    files = SimpleNamespace(
        resolve_many=AsyncMock(
            side_effect=[[], resolved_rows]
            if historical
            else None,
            return_value=resolved_rows,
        ),
        public_file=lambda row: {
            "id": row["id"],
            "name": row["file_name"],
            "type": row["mime_type"],
            "size": int(row.get("size_bytes") or 0),
            "url": f'/api/files/{row["id"]}/content',
        },
    )
    ai = SimpleNamespace(
        settings=SimpleNamespace(
            brave_api_key=None,
            web_search_enabled=False,
            anthropic_model="test-chat-model",
        ),
        needs_external_lookup=lambda _message: False,
        chat=AsyncMock(return_value={"response": "chat response", "model": "test-chat-model"}),
    )

    monkeypatch.setattr(chat_routes, "db", GateDB())
    monkeypatch.setattr(chat_routes, "media", media)
    monkeypatch.setattr(chat_routes, "features", features)
    monkeypatch.setattr(chat_routes, "files", files)
    monkeypatch.setattr(chat_routes, "ai", ai)
    monkeypatch.setattr(chat_routes, "intelligence", intelligence)
    monkeypatch.setattr(chat_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(chat_routes, "apply_project_context", AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, "mark_check_in_responded", AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, "record_product_event", AsyncMock(return_value=True))
    return media, features, intelligence


def _payload(message, **extra):
    return {
        "message": message,
        "fileRefs": [row["id"] for row in IMAGE_ROWS],
        "imageReferenceContractVersion": 2,
        **extra,
    }


def test_contract_capability_does_not_promote_ordinary_image_analysis(monkeypatch) -> None:
    media, features, intelligence = _install_route_doubles(monkeypatch, None)

    response = CLIENT.post("/api/chat", json=_payload("What details do you see in these images?"))

    assert response.status_code == 200
    assert response.json()["response"] == "I analyzed the attached images."
    media.plan.assert_not_called()
    media.generate_or_edit_image.assert_not_awaited()
    media.understand.assert_awaited_once()
    intelligence.prepare.assert_awaited_once()
    features.consume_message.assert_awaited_once()


def test_raw_explicit_image_request_requires_confirmation_before_intelligence_or_usage(monkeypatch) -> None:
    media, features, intelligence = _install_route_doubles(monkeypatch, None)

    response = CLIENT.post("/api/chat", json=_payload("Generate a promo image from these assets"))

    assert response.status_code == 400
    assert response.json()["code"] == "IMAGE_REFERENCE_CONFIRMATION_REQUIRED"
    media.plan.assert_called_once()
    intelligence.prepare.assert_not_awaited()
    features.authorize.assert_not_awaited()
    features.consume_message.assert_not_awaited()
    features.consume.assert_not_awaited()


def test_subtle_semantic_image_execution_requires_confirmation_before_usage(monkeypatch) -> None:
    intent = {
        "kind": "image",
        "stage": "execute",
        "brief": "Place the supplied product and mark in a restrained moonlit campaign scene.",
    }
    media, features, intelligence = _install_route_doubles(monkeypatch, intent)

    response = CLIENT.post(
        "/api/chat",
        json=_payload("Put these together in a restrained moonlit campaign scene."),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IMAGE_REFERENCE_CONFIRMATION_REQUIRED"
    media.plan.assert_called_once()
    intelligence.prepare.assert_awaited_once()
    media.generate_or_edit_image.assert_not_awaited()
    features.authorize.assert_not_awaited()
    features.consume_message.assert_not_awaited()
    features.consume.assert_not_awaited()


def test_confirmed_semantic_reference_plan_proceeds_in_attachment_order(monkeypatch) -> None:
    intent = {
        "kind": "image",
        "stage": "execute",
        "brief": "Place the supplied product and mark in a restrained moonlit campaign scene.",
    }
    media, features, _intelligence = _install_route_doubles(monkeypatch, intent)
    plan = [
        {"fileId": IMAGE_ROWS[0]["id"], "role": "base"},
        {"fileId": IMAGE_ROWS[1]["id"], "role": "logo"},
    ]

    response = CLIENT.post(
        "/api/chat",
        json=_payload(
            "Put these together in a restrained moonlit campaign scene.",
            imageReferencePlan=plan,
            imageReferencePlanConfirmed=True,
            imageUseReference=True,
        ),
    )

    assert response.status_code == 200
    assert response.json()["referencePlan"] == [
        {"fileId": IMAGE_ROWS[0]["id"], "role": "base", "input": 1},
        {"fileId": IMAGE_ROWS[1]["id"], "role": "logo", "input": 2},
    ]
    media.generate_or_edit_image.assert_awaited_once()
    features.authorize.assert_awaited_once()
    features.consume_message.assert_awaited_once()
    features.consume.assert_awaited_once()


def test_older_client_semantic_image_request_keeps_legacy_reference_defaults(monkeypatch) -> None:
    intent = {
        "kind": "image",
        "stage": "execute",
        "brief": "Place the supplied product in a restrained campaign scene.",
    }
    media, features, _intelligence = _install_route_doubles(monkeypatch, intent)

    response = CLIENT.post(
        "/api/chat",
        json={
            "message": "Put these together in a restrained campaign scene.",
            "fileRefs": [row["id"] for row in IMAGE_ROWS],
        },
    )

    assert response.status_code == 200
    assert response.json()["referencePlan"] == [
        {"fileId": IMAGE_ROWS[0]["id"], "role": "base", "input": 1},
        {"fileId": IMAGE_ROWS[1]["id"], "role": "subject", "input": 2},
    ]
    media.generate_or_edit_image.assert_awaited_once()
    features.consume_message.assert_awaited_once()


def test_implicit_historical_edit_returns_no_charge_reference_handoff(monkeypatch) -> None:
    media, features, intelligence = _install_route_doubles(monkeypatch, None, historical=True)

    response = CLIENT.post(
        "/api/chat",
        json={
            "message": "Change that image background to a moonlit studio.",
            "history": [{"role": "assistant", "content": "Prior image", "fileRefs": [row["id"] for row in IMAGE_ROWS]}],
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "IMAGE_REFERENCE_CONFIRMATION_REQUIRED"
    assert body["referenceHandoff"] == {
        "kind": "image_reference_plan",
        "source": "conversation_history",
        "noCharge": True,
        "files": [
            {
                "id": row["id"],
                "name": row["file_name"],
                "type": row["mime_type"],
                "size": 0,
                "url": f'/api/files/{row["id"]}/content',
            }
            for row in IMAGE_ROWS
        ],
    }
    media.plan.assert_not_called()
    media.generate_or_edit_image.assert_not_awaited()
    intelligence.prepare.assert_not_awaited()
    features.authorize.assert_not_awaited()
    features.consume_message.assert_not_awaited()
    features.consume.assert_not_awaited()


def test_historical_image_analysis_remains_analysis(monkeypatch) -> None:
    media, features, intelligence = _install_route_doubles(monkeypatch, None, historical=True)

    response = CLIENT.post(
        "/api/chat",
        json={
            "message": "What do you see in the image above?",
            "history": [{"role": "assistant", "content": "Prior image", "fileRefs": [row["id"] for row in IMAGE_ROWS]}],
        },
    )

    assert response.status_code == 200
    assert response.json()["response"] == "I analyzed the attached images."
    media.plan.assert_not_called()
    media.generate_or_edit_image.assert_not_awaited()
    media.understand.assert_awaited_once()
    intelligence.prepare.assert_awaited_once()
    features.consume_message.assert_awaited_once()


@pytest.mark.parametrize(
    "plan",
    [
        [
            {"fileId": IMAGE_ROWS[1]["id"], "role": "logo"},
            {"fileId": IMAGE_ROWS[0]["id"], "role": "base"},
        ],
        [
            {"fileId": IMAGE_ROWS[0]["id"], "role": "base"},
            {"fileId": "33333333-3333-4333-8333-333333333333", "role": "logo"},
        ],
    ],
    ids=["swapped-order", "stale-file"],
)
def test_confirmed_reference_plan_rejects_swapped_or_stale_order_before_usage(monkeypatch, plan) -> None:
    media, features, intelligence = _install_route_doubles(monkeypatch, None)

    response = CLIENT.post(
        "/api/chat",
        json=_payload(
            "Generate a promo image from these assets",
            imageReferencePlan=plan,
            imageReferencePlanConfirmed=True,
            imageUseReference=True,
        ),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "IMAGE_REFERENCE_PLAN_INVALID"
    assert "order" in response.json()["message"].lower()
    media.generate_or_edit_image.assert_not_awaited()
    intelligence.prepare.assert_not_awaited()
    features.authorize.assert_not_awaited()
    features.consume_message.assert_not_awaited()
    features.consume.assert_not_awaited()


def test_modern_client_advertises_reference_contract_without_forcing_image_mode() -> None:
    script = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")
    builder = script[script.index("function buildRequestBody") : script.index("async function ensureUsage")]
    sender = script[script.index("async function studioSendMessage") : script.index("async function retryMessage")]

    capability = "if (attachedImages.length) body.imageReferenceContractVersion = 2;"
    assert capability in builder
    assert builder.index(capability) < builder.index("if (state.tool === 'image')")
    assert "...(ready.some(isImageAttachment) ? {imageReferenceContractVersion:2} : {})," in sender
    assert "if (IMAGE_REFERENCE_PLAN_CODES.has(error.code)) {" in sender
    assert "referencePlanRecoveryMessage = target;" in sender
    assert sender.index("referencePlanRecoveryMessage = target") < sender.index("reopenImageReferencePlan(referencePlanRecoveryMessage)")
    recovery = script[script.index("function reopenImageReferencePlan") : script.index("async function retryMessage")]
    assert "const references = (message.files || []).filter" in recovery
    assert "references.forEach((file, index) => addRemoteReference(file" in recovery
    assert "invalidateImageReferencePlan();" in recovery
    assert "safeImageReferenceHandoff(error.data?.referenceHandoff)" in sender
    assert "if (handoffFiles.length) target.files = handoffFiles;" in sender


def test_retry_reopens_an_owner_resolved_reference_handoff() -> None:
    script = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")
    retry = script[script.index("async function retryMessage") : script.index("function reviseImageMessage")]

    assert "safeImageReferenceHandoff(error.data?.referenceHandoff)" in retry
    assert "if (handoffFiles.length) message.files = handoffFiles;" in retry
    assert "referencePlanRecoveryMessage = message;" in retry
    assert retry.index("referencePlanRecoveryMessage = message") < retry.index(
        "reopenImageReferencePlan(referencePlanRecoveryMessage)"
    )


def test_client_confirmation_is_bound_to_the_exact_ordered_reference_plan() -> None:
    script = (ROOT / "public" / "crump-5.0.js").read_text(encoding="utf-8")
    attachment_mutations = script[script.index("function addRemoteReference") : script.index("function activeToolLabel")]
    reference_contract = script[script.index("function imageReferencePlan(") : script.index("function showDocumentOptions")]
    sender = script[script.index("async function studioSendMessage") : script.index("async function retryMessage")]

    assert "if (isImageAttachment(item)) invalidateImageReferencePlan();" in attachment_mutations
    assert "if (isSupportedImageFile(file)) invalidateImageReferencePlan();" in attachment_mutations
    assert "state.imageReferencePlanSignature === JSON.stringify(plan)" in reference_contract
    assert "state.imageReferencePlanSignature = currentReferences.length ? JSON.stringify(confirmedPlan) : '';" in reference_contract
    assert "!imageReferencePlanIsConfirmed(draftReferences)" in sender
    assert "imageReferencePlanConfirmed:imageReferencePlanIsConfirmed(ready)" in sender
