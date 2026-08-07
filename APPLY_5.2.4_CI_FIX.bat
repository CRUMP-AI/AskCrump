@echo off
setlocal
cd /d "%~dp0"

echo.
echo Ask Crump 5.2.4 CI Cleanup
echo --------------------------
echo Removing the two Ruff-confirmed unused Python imports...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$files=@('backend\intelligence_service.py','backend\crump52_patches.py');" ^
  "foreach($file in $files) {" ^
  "  if(-not (Test-Path $file)){ throw ('Missing required file: ' + $file) };" ^
  "  $text=[System.IO.File]::ReadAllText((Resolve-Path $file));" ^
  "  $updated=[regex]::Replace($text,'(?m)^import json\r?\n','',1);" ^
  "  if($updated -eq $text){ throw ('Expected unused import not found in: ' + $file) };" ^
  "  [System.IO.File]::WriteAllText((Resolve-Path $file),$updated,(New-Object System.Text.UTF8Encoding($false)));" ^
  "}"

if errorlevel 1 (
  echo.
  echo Cleanup failed. Nothing else should be committed yet.
  pause
  exit /b 1
)

echo.
echo Python lint cleanup applied successfully.
echo package.json and scripts\check-javascript.mjs were already restored by this patch.
echo.
echo You can now commit and push.
echo Suggested commit summary:
echo Fix 5.2.4 CI checks and restore native dependencies
echo.
pause

del "%~f0"
