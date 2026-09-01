from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_mobile_crump50_sheet_does_not_keep_desktop_horizontal_translation():
    css = read("public/crump-v1-body.css")

    assert "Mobile sheets use full-width edge anchoring." in css
    assert "body.crump-v1-body .crump50-sheet {" in css
    assert "transform: translateY(18px) scale(.985) !important;" in css
    assert "overflow-x: hidden !important;" in css
    assert "body.crump-v1-body .crump50-sheet.is-visible {" in css
    assert "transform: translateY(0) scale(1) !important;" in css


def test_mobile_document_format_grid_remains_two_columns_and_complete():
    css = read("public/crump-5.0.css")
    script = read("public/crump-5.0.js")

    assert "body.crump-50 .crump50-format-grid { grid-template-columns: repeat(2,1fr); }" in css

    start = script.index("function showDocumentOptions()")
    end = script.index("function openCamera()", start)
    document_tool = script[start:end]

    assert "DOCUMENT STUDIO" in document_tool
    assert "Start with the outcome. Crump will structure the file." in document_tool
    assert "What are you making?" in document_tool
    assert "ESSAY · REPORT" in document_tool
    assert "RÉSUMÉ · CV" in document_tool
    assert "PRESENTATION" in document_tool
    assert "SPREADSHEET" in document_tool
    assert "MANUSCRIPT" in document_tool
    assert "[['docx','Word','DOCX'],['pdf','PDF','PDF'],['pptx','PowerPoint','PPTX'],['xlsx','Excel','XLSX'],['md','Markdown','MD'],['txt','Text','TXT']]" in document_tool
    assert "state.tool = 'document'" in document_tool
    assert "state.documentFormat = value" in document_tool


def test_document_and_attachment_sheets_are_contained_recoverable_dialogs():
    script = read("public/crump-5.0.js")
    verifier = read("scripts/verify-creation-sheet-containment.cjs")
    fixture = read("tests/fixtures/creation-sheet-containment.html")
    document_tool = script[
        script.index("function showDocumentOptions()") : script.index("function openCamera()")
    ]
    attachment_tool = script[
        script.index("function showAttachMenu()") : script.index("function segmented(")
    ]

    for contract in (
        "sheet.setAttribute('role', 'dialog')",
        "sheet.setAttribute('aria-modal', 'true')",
        "sheet.tabIndex = -1",
        "wireMenuKeyboard(sheet, dismiss)",
        "mountMenu(sheet, close)",
    ):
        assert contract in document_tool
        assert contract in attachment_tool
    assert "aria-labelledby', 'crump50DocumentStudioTitle" in document_tool
    assert "aria-label', 'Close Document Studio" in document_tool
    assert "restoreMenuFocus(returnFocus)" in document_tool
    assert "aria-label', 'Close Add to conversation" in attachment_tool
    assert "isolateMenuBackground(sheet)" in script
    assert "restoreMenuBackground()" in script
    assert "containMenuFocus(event, sheet)" in script
    assert "fixtureSidebar" in fixture
    assert "fixtureWorkspace" in fixture
    assert "fixtureNavigation" in fixture
    assert "assertIsolated" in verifier
    assert "assertRestored" in verifier
    assert "Shift+Tab" in verifier
    assert "Close Document Studio" in verifier
    assert "Close Add to conversation" in verifier


def test_intelligence_glasses_have_slightly_more_visual_presence():
    intelligence = read("public/crump-4.4.js")

    assert 'class="crump44-glasses-icon" width="23" height="23"' in intelligence
    assert 'class="crump44-glasses-icon" width="20" height="20"' not in intelligence


def test_documents_mobile_hotfix_advances_shell_cache():
    sw = read("public/sw.js")
    checker = read("scripts/check-javascript.mjs")
    runtime = read("public/runtime-body-v1.js")
    legacy_config = read("public/runtime-config.js")
    v1_config = read("public/runtime-config-v1.js")
    native = read("scripts/build-native.mjs")

    assert "ask-crump-new-body-v1-r208" in sw
    assert "ask-crump-new-body-v1-r21" not in sw
    assert "ask-crump-new-body-v1-r208" in checker
    exact_asset = "/crump-5.0.js?v=5.9.76-image-reference-recovery-1"
    for source in (sw, runtime, legacy_config, v1_config, native):
        assert exact_asset in source
