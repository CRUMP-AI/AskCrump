from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_public(name: str) -> str:
    return (ROOT / "public" / name).read_text(encoding="utf-8")


def test_video_studio_names_the_project_destination_and_offers_files_only():
    product = read_public("crump-product-5.3.js")
    assert 'id="crump53VideoProjectContext" hidden' in product
    assert 'id="crump53VideoProjectName"' in product
    assert 'id="crump53VideoProjectClear"' in product
    assert "The finished video will appear in this Project and in your private Files." in product
    assert "Use Files only" in product
    assert "renderVideoProjectDestination();" in product
    assert "clearActiveProject({announce: true});" in product
    assert "projectId: state.activeProject?.id || null" in product


def test_video_project_destination_is_responsive_and_hidden_when_inactive():
    styles = read_public("crump-product-5.3.css")
    assert ".crump53-video-project-context[hidden] { display: none; }" in styles
    assert "body.crump-v1-body .crump53-video-project-context" in styles
    assert "flex-direction: column;" in styles
