from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def packet() -> str:
    return (ROOT / "docs/SOCIAL_LAUNCH_BATCH_2026-08-29.md").read_text(encoding="utf-8")


def test_social_launch_packet_prevents_duplicate_workspace_posts():
    text = packet()

    assert text.count("Status: already live; retain as a historical campaign reference and do not republish.") == 2
    assert "## Remaining publication 1 — Facebook — presentation outcome" in text
    assert "## Remaining publication 2 — Instagram — presentation outcome" in text
    assert "Publish only the two remaining presentation messages, one per platform." in text
    assert "Publish the workspace message first on both platforms." not in text


def test_social_launch_packet_uses_one_exact_measurable_approval_contract():
    text = packet()
    approval = (
        "Apply the tracked profile links, submit the Ask Crump sitemap, "
        "publish the presentation batch, and send the progress update."
    )

    assert text.count(approval) == 1
    assert "https://www.askcrump.com/?acquisition=facebook&source=profile-link" in text
    assert (
        "https://www.askcrump.com/ai-presentation-maker?"
        "acquisition=instagram&source=profile-link"
    ) in text
    assert "https://www.askcrump.com/sitemap.xml" in text
    assert "point either cold campaign directly to `/app`" in text
