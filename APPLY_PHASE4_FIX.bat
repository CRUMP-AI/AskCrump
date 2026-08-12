@echo off
setlocal
cd /d "%~dp0"
echo.
echo Ask Crump - Phase 4 source fix
echo --------------------------------
echo This will modify only the audited CI source files and remove the old Phase 4 handoff artifacts.
echo.
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0_phase4_fix.py"
) else (
  python "%~dp0_phase4_fix.py"
)
set EXITCODE=%errorlevel%
echo.
if not %EXITCODE%==0 (
  echo Fix did NOT complete. No validated source change should remain.
  pause
  exit /b %EXITCODE%
)

del /q "%~dp0_phase4_fix.py" >nul 2>nul
echo Success. The temporary helper files will clean themselves up.
echo Return to GitHub Desktop and review the source changes.
echo.
pause
(goto) 2>nul & del "%~f0"
