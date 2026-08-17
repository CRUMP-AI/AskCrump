param(
    [string]$KeystorePath = (Join-Path $env:USERPROFILE '.askcrump\signing\android\askcrump-upload.jks'),
    [string]$Alias = 'upload'
)

$ErrorActionPreference = 'Stop'

$privateJdk = Join-Path $env:LOCALAPPDATA 'AskCrump\toolchain\jdk-21'
$keytool = Join-Path $privateJdk 'bin\keytool.exe'

if (-not (Test-Path -LiteralPath $keytool)) {
    throw "Ask Crump private JDK 21 keytool was not found at $keytool"
}

$directory = Split-Path -Parent $KeystorePath
New-Item -ItemType Directory -Force -Path $directory | Out-Null

if (Test-Path -LiteralPath $KeystorePath) {
    throw "Refusing to overwrite existing upload keystore: $KeystorePath"
}

Write-Host ''
Write-Host 'ASK CRUMP — GOOGLE PLAY UPLOAD KEY' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Java keytool will prompt you for a password.' -ForegroundColor White
Write-Host 'Choose a strong password and store it in your password manager.' -ForegroundColor Yellow
Write-Host 'Do NOT send the password to Echo or place it in GitHub.' -ForegroundColor Yellow
Write-Host ''

& $keytool `
    -genkeypair `
    -v `
    -keystore $KeystorePath `
    -storetype JKS `
    -alias $Alias `
    -keyalg RSA `
    -keysize 4096 `
    -validity 10000 `
    -dname 'CN=Ask Crump Upload Key'

if ($LASTEXITCODE -ne 0) {
    throw 'keytool did not create the Ask Crump upload keystore.'
}

$certificatePath = Join-Path $directory 'askcrump-upload-certificate.pem'

Write-Host ''
Write-Host 'The private upload key was created.' -ForegroundColor Green
Write-Host 'Exporting the PUBLIC upload certificate next.' -ForegroundColor Cyan
Write-Host 'keytool will request the keystore password again.' -ForegroundColor White
Write-Host ''

& $keytool `
    -exportcert `
    -rfc `
    -keystore $KeystorePath `
    -storetype JKS `
    -alias $Alias `
    -file $certificatePath

if ($LASTEXITCODE -ne 0) {
    throw 'Public upload certificate export failed.'
}

$note = Join-Path $directory 'BACKUP_REQUIRED.txt'
@"
ASK CRUMP GOOGLE PLAY UPLOAD KEY

PRIVATE KEY:
$KeystorePath

PUBLIC CERTIFICATE:
$certificatePath

Alias:
$Alias

The .jks file and its password are required for future Google Play uploads.
Back up the .jks in company-controlled secure storage.
Never commit the .jks or passwords to GitHub.
"@ | Set-Content -LiteralPath $note -Encoding UTF8

Write-Host ''
Write-Host 'PASS : Upload keystore created outside the Ask Crump repository.' -ForegroundColor Green
Write-Host "PRIVATE KEY : $KeystorePath" -ForegroundColor White
Write-Host "PUBLIC CERT: $certificatePath" -ForegroundColor White
Write-Host ''
