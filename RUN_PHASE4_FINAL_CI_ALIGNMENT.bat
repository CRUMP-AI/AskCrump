@echo off
setlocal
cd /d "%~dp0"
title Ask Crump - Phase 4 FINAL CI Alignment
echo.
echo Ask Crump Phase 4 - final CI contract alignment
echo No Python, command-line Git, or Node is required.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0phase4_final_ci_alignment.ps1"
echo.
pause
