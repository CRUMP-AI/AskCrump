@echo off
setlocal
cd /d "%~dp0"

echo.
echo Ask Crump V1 Revamp
echo ===================
echo Applying the canonical V1 shell to public\app.html...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$path='public\app.html';" ^
  "if(-not (Test-Path $path)){ throw 'Missing public\app.html' };" ^
  "$text=[System.IO.File]::ReadAllText((Resolve-Path $path));" ^
  "$original=$text;" ^
  "$text=[regex]::Replace($text,'<script defer src=\"/runtime-config(?:-brand-safe)?\.js\"></script>','<script defer src=\"/runtime-config-v1.js\"></script>');" ^
  "if($text -notmatch '/crump-v1\.css') {" ^
  "  $text=$text.Replace('<link rel=\"stylesheet\" href=\"/auth-styles.css\">','<link rel=\"stylesheet\" href=\"/auth-styles.css\">`r`n<link rel=\"stylesheet\" href=\"/crump-v1.css\" data-crump-v1=\"true\">');" ^
  "}" ^
  "$text=$text.Replace('<body>','<body class=\"crump-v1\">');" ^
  "$text=$text.Replace('/assets/ask-crump-logo.png','/assets/brand/crump-horizontal-light.png');" ^
  "$text=$text.Replace('/assets/ask-crump-header.png','/assets/brand/crump-horizontal-light.png');" ^
  "$text=$text.Replace('/assets/logo-c.png','/assets/brand/crump-mark.png');" ^
  "$text=$text.Replace('Upgrade Subscription','Plan & credits');" ^
  "$text=[regex]::Replace($text,'accept=\"image/\*,\.pdf\"','accept=\"image/*,.pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.tsv,.json,.html,.rtf\"');" ^
  "$text=[regex]::Replace($text,'\s*<link rel=\"preconnect\" href=\"https://fonts\.googleapis\.com\">\s*','`r`n');" ^
  "$text=[regex]::Replace($text,'\s*<link rel=\"preconnect\" href=\"https://fonts\.gstatic\.com\" crossorigin>\s*','`r`n');" ^
  "$text=[regex]::Replace($text,'\s*<link href=\"https://fonts\.googleapis\.com/css2\?[^>]+rel=\"stylesheet\">\s*','`r`n');" ^
  "if($text -notmatch '<meta name=\"theme-color\"') {" ^
  "  $text=$text.Replace('<title>Ask Crump</title>','<title>Ask Crump</title>`r`n<meta name=\"theme-color\" content=\"#080b0f\">');" ^
  "}" ^
  "if($text -eq $original){ throw 'No app.html changes were applied. Stop and tell Echo.' };" ^
  "[System.IO.File]::WriteAllText((Resolve-Path $path),$text,(New-Object System.Text.UTF8Encoding($false)));"

if errorlevel 1 (
  echo.
  echo REVAMP PATCH FAILED.
  echo Do not commit yet. Send Echo a screenshot of this window.
  pause
  exit /b 1
)

echo.
echo V1 shell patch applied successfully.
echo.
echo Suggested commit summary:
echo Ask Crump V1 interface revamp
echo.
pause
del "%~f0"
