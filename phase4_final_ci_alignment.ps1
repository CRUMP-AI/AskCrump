$ErrorActionPreference = "Stop"

$Repo = "C:\Users\gcrum\OneDrive\Documents\GitHub\CRUMP-AI-Portfolio-Upload"

function Is-Repo([string]$Path) {
    return (
        (Test-Path -LiteralPath $Path -PathType Container) -and
        (Test-Path -LiteralPath (Join-Path $Path "tests\test_sidebar_navigation.py")) -and
        (Test-Path -LiteralPath (Join-Path $Path "scripts\check-javascript.mjs")) -and
        (Test-Path -LiteralPath (Join-Path $Path "public\crump-navigation-5.2.5.js")) -and
        (Test-Path -LiteralPath (Join-Path $Path "public\sw.js"))
    )
}

if (-not (Is-Repo $Repo)) {
    Write-Host "Expected repo not found at:"
    Write-Host "  $Repo"
    Write-Host ""
    $Repo = (Read-Host "Paste the CRUMP-AI repository folder path").Trim('"')
    if (-not (Is-Repo $Repo)) {
        Write-Host "ERROR: That folder does not match the Ask Crump repository."
        exit 2
    }
}

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Read-Utf8([string]$Path) {
    [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}
function Write-Utf8([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

$TestPath = Join-Path $Repo "tests\test_sidebar_navigation.py"
$CheckerPath = Join-Path $Repo "scripts\check-javascript.mjs"
$SwPath = Join-Path $Repo "public\sw.js"
$NavPath = Join-Path $Repo "public\crump-navigation-5.2.5.js"

$BeforeTest = Read-Utf8 $TestPath
$BeforeChecker = Read-Utf8 $CheckerPath

Write-Host ""
Write-Host "========================================================="
Write-Host " Ask Crump - Phase 4 FINAL CI Alignment"
Write-Host "========================================================="
Write-Host ""
Write-Host "Repository: $Repo"
Write-Host ""
Write-Host "This changes ONLY:"
Write-Host "  tests/test_sidebar_navigation.py"
Write-Host "  scripts/check-javascript.mjs"
Write-Host ""
Write-Host "No production UI file is modified."
Write-Host ""

try {
    $ExpectedTest = @'
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"


def read_public(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


def test_settings_and_billing_keep_one_primary_sidebar_destination_each():
    html = read_public("app.html")
    cleanup = read_public("crump-navigation-5.2.5.js")
    cleanup_css = read_public("crump-navigation-5.2.5.css")

    # The labeled sidebar rows remain the single user-facing destinations.
    assert html.count('id="settingsBtn"') == 1
    assert html.count('id="upgradeBtnSidebar"') == 1
    assert "<span>Settings</span>" in html
    assert "<span>Plan & credits</span>" in html

    # The final navigation layer removes the legacy icon-only rail duplicates.
    assert '.v1-rail [data-v1-command="settings"]' in cleanup
    assert '.v1-rail [data-v1-command="billing"]' in cleanup
    assert ".forEach(node => node.remove())" in cleanup
    assert "document.querySelector('.v1-rail .v1-rail-spacer')?.remove();" in cleanup

    # Defense in depth prevents those legacy controls flashing before JS cleanup.
    assert 'body.crump-v1-body .v1-rail [data-v1-command="settings"]' in cleanup_css
    assert 'body.crump-v1-body .v1-rail [data-v1-command="billing"]' in cleanup_css
    assert "display: none !important;" in cleanup_css


def test_footer_normalization_removes_decorative_destination_icons():
    cleanup = read_public("crump-navigation-5.2.5.js")

    assert "normalizeFooterDestination('settingsBtn', 'Settings')" in cleanup
    assert "normalizeFooterDestination('upgradeBtnSidebar', 'Plan & credits')" in cleanup
    assert "button.querySelector(':scope > svg')?.remove();" in cleanup


def test_credit_badge_remains_attached_and_mobile_destination_click_closes_drawer():
    billing_js = read_public("crump-billing-5.1.js")
    billing_css = read_public("crump-billing-5.1.css")
    cleanup = read_public("crump-navigation-5.2.5.js")
    cleanup_css = read_public("crump-navigation-5.2.5.css")

    assert "const button = $('#upgradeBtnSidebar');" in billing_js
    assert "button.appendChild(badge);" in billing_js
    assert "function closeMobileSidebar()" in cleanup
    assert "#settingsBtn, #upgradeBtnSidebar" in cleanup
    assert "byId('sidebar')?.classList.remove('active');" in cleanup
    assert "byId('sidebarOverlay')?.classList.remove('active');" in cleanup
    assert "#upgradeBtnSidebar .billing51-sidebar-balance" in billing_css
    assert "#upgradeBtnSidebar .billing51-sidebar-balance" in cleanup_css
    assert "margin-left: auto" in cleanup_css
'@
    Write-Utf8 $TestPath $ExpectedTest

    $checker = Read-Utf8 $CheckerPath
    $old = "serviceWorker.includes('ask-crump-new-body-v1-r2')"
    $new = "serviceWorker.includes('ask-crump-new-body-v1-r3')"

    if ($checker.Contains($old)) {
        $first = $checker.IndexOf($old)
        $second = $checker.IndexOf($old, $first + $old.Length)
        if ($second -ge 0) {
            throw "Unexpected number of r2 service-worker contract matches."
        }
        $checker = $checker.Replace($old, $new)
        Write-Utf8 $CheckerPath $checker
    } elseif ($checker.Contains($new)) {
        Write-Host "JavaScript checker already expects r3."
    } else {
        throw "The service-worker contract line has diverged from the audited main branch."
    }

    $testNow = Read-Utf8 $TestPath
    $checkerNow = Read-Utf8 $CheckerPath
    $sw = Read-Utf8 $SwPath
    $nav = Read-Utf8 $NavPath

    if (-not $sw.Contains("ask-crump-new-body-v1-r3")) {
        throw "public/sw.js is not using the approved r3 cache."
    }
    if (-not $checkerNow.Contains("serviceWorker.includes('ask-crump-new-body-v1-r3')")) {
        throw "CI checker was not aligned to r3."
    }
    if ($checkerNow.Contains("serviceWorker.includes('ask-crump-new-body-v1-r2')")) {
        throw "Obsolete r2 CI expectation still remains."
    }
    if (-not $nav.Contains("removeDuplicateRailDestinations")) {
        throw "Current navigation cleanup runtime is missing."
    }
    if (-not $nav.Contains("#settingsBtn, #upgradeBtnSidebar")) {
        throw "Current mobile sidebar-close contract is missing."
    }
    if (-not $testNow.Contains("test_settings_and_billing_keep_one_primary_sidebar_destination_each")) {
        throw "Updated sidebar regression test did not validate."
    }
    if ($testNow.Contains("assert 'data-v1-command=`"settings`"' not in html")) {
        throw "Obsolete static-DOM sidebar assertion remains."
    }

    Write-Host "Validation: PASS" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Rolling both files back..."
    Write-Utf8 $TestPath $BeforeTest
    Write-Utf8 $CheckerPath $BeforeChecker
    Write-Host "Rollback complete. Nothing partial remains."
    exit 3
}

Write-Host ""
Write-Host "========================================================="
Write-Host " SUCCESS - FINAL PHASE 4 CI ALIGNMENT APPLIED"
Write-Host "========================================================="
Write-Host ""
Write-Host "Open GitHub Desktop."
Write-Host "You should see ONLY these two modified files:"
Write-Host "  tests/test_sidebar_navigation.py"
Write-Host "  scripts/check-javascript.mjs"
Write-Host ""
Write-Host "Commit title:"
Write-Host "  Align Phase 4 regression contracts"
Write-Host ""
Write-Host "Push origin, then tell Echo:"
Write-Host "  Phase 4 final CI alignment pushed."
