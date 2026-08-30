from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def packet() -> str:
    return (ROOT / "docs/SOCIAL_LAUNCH_BATCH_2026-08-29.md").read_text(encoding="utf-8")


def test_social_launch_packet_prevents_duplicate_workspace_posts():
    text = packet()

    assert text.count("Status: already live; retain as a historical campaign reference and do not republish.") == 2
    assert "**Superseded — do not use this packet to publish the presentation pair.**" in text
    assert "## Retired reference — Facebook — presentation outcome" in text
    assert "## Retired reference — Instagram — presentation outcome" in text
    assert "Status: do not publish; use the current marketing-owned replacement package after review." in text
    assert "Status: do not publish; this asset visibly carries the retired descriptor." in text
    assert "Publish the workspace message first on both platforms." not in text
    assert "## Remaining publication" not in text


def test_social_launch_packet_voids_old_approval_and_points_to_current_action_record():
    text = packet()
    normalized = " ".join(text.split())
    void_approval = (
        "Apply the tracked profile links, submit the Ask Crump sitemap, "
        "publish the presentation batch, and send the progress update."
    )

    assert void_approval not in text
    assert "The original action-time approval phrase in this file is therefore void." in text
    assert "ask-crump-marketing/campaigns/presentation-proof-current/final" in text
    assert "ask-crump-marketing/handoffs/PRESENTATION_BATCH_REPLACEMENT.md" in text
    assert "record neither copies the marketing assets nor authorizes publishing them" in text
    assert "Do not publish either product-repository presentation asset" in text
    assert "https://www.askcrump.com/?acquisition=facebook&source=profile-link" in text
    assert (
        "https://www.askcrump.com/ai-presentation-maker?"
        "acquisition=instagram&source=profile-link"
    ) in text
    assert "verified Search Console property has no submitted sitemap" in normalized
    assert "Keep profile-link, Search Console, publication, and campaign-spend actions" in text
