@echo off
setlocal
cd /d "%~dp0"
title Ask Crump - Phase 4 Final Auto Fix
echo.
echo =========================================================
echo Ask Crump - Phase 4 FINAL source fix
echo =========================================================
echo.
echo IMPORTANT: Keep this extracted folder OUTSIDE the CRUMP-AI repository.
echo This tool will locate the real GitHub Desktop repository for you.
echo.
where py >nul 2>nul
if %errorlevel%==0 (
    py "%~dp0phase4_final_fix.py"
) else (
    python "%~dp0phase4_final_fix.py"
)
set EXITCODE=%errorlevel%
echo.
if not %EXITCODE%==0 (
    echo The fix did not complete. Read the message above.
) else (
    echo Done. Return to GitHub Desktop.
)
echo.
pause
exit /b %EXITCODE%
