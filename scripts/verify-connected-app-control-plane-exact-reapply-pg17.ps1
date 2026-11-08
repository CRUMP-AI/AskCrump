param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 55449,
    [string]$UserName = "postgres",
    [string]$Password = "postgres",
    [string]$PgBin = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PgBin) {
    $PgBin = (Resolve-Path (Join-Path $repoRoot "..\local-pg17-test-20261022\runtime\pgsql\bin")).Path
}
$psql = Join-Path $PgBin "psql.exe"
$createdb = Join-Path $PgBin "createdb.exe"
$dropdb = Join-Path $PgBin "dropdb.exe"
$pgdump = Join-Path $PgBin "pg_dump.exe"
$migration = Join-Path $repoRoot "migrations\20261107190000_connected_app_control_plane.sql"
$env:PGPASSWORD = $Password
$suffix = "{0:x}" -f $PID
$templateDb = "connected_base_exact_$suffix"
$created = [System.Collections.Generic.List[string]]::new()

function Invoke-NativeChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "native command failed: $Executable $($Arguments -join ' ')"
    }
}

function Invoke-Sql {
    param([string]$Database, [string]$Sql)
    Invoke-NativeChecked $psql @(
        "-X", "-q", "-v", "ON_ERROR_STOP=1",
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $Database, "-c", $Sql
    )
}

function Get-SchemaDigest {
    param([string]$Database)
    $dump = & $pgdump @(
        "--schema-only",
        "--schema=connected_app_private", "--schema=public",
        "-h", $HostName, "-p", "$Port", "-U", $UserName, $Database
    ) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed for $Database" }
    # PostgreSQL 17 emits a fresh psql \restrict token in every dump.  It is
    # transport noise, not database state, so remove only those two lines.
    $stableDump = (($dump -split "`r?`n") |
        Where-Object { $_ -notmatch '^\\(un)?restrict\s' }) -join "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($stableDump)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash($bytes)
    }
    finally {
        $hasher.Dispose()
    }
    return ([BitConverter]::ToString($digest)).Replace("-", "")
}

function Assert-DriftRefused {
    param([string]$Name, [string]$Sql)
    $database = "connected_base_${Name}_$suffix"
    if ($database.Length -gt 63) { throw "test database name is too long: $database" }
    Invoke-NativeChecked $createdb @(
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "--template", $templateDb, $database
    )
    $created.Add($database)
    Invoke-Sql $database $Sql
    $before = Get-SchemaDigest $database
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $psql @(
            "-X", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $database, "-f", $migration
        ) 2>&1 | Out-String
        $psqlExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($psqlExitCode -eq 0) { throw "drift unexpectedly reapplied: $Name" }
    if ($output -notmatch "55000" -or $output -notmatch "refusing repair") {
        throw "drift did not fail with the exact refusal contract: $Name`n$output"
    }
    $after = Get-SchemaDigest $database
    if ($before -ne $after) { throw "drift was mutated before refusal: $Name" }
    Write-Host "PASS drift refusal/no-repair: $Name"
}

try {
    & $dropdb -h $HostName -p "$Port" -U $UserName --if-exists $templateDb | Out-Null
    Invoke-NativeChecked $createdb @("-h", $HostName, "-p", "$Port", "-U", $UserName, $templateDb)
    $created.Add($templateDb)
    Invoke-Sql $templateDb @"
create table public.users(id uuid primary key);
create table public.sessions(
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  expires_at timestamptz not null,
  revoked_at timestamptz
);
"@
    Invoke-NativeChecked $psql @(
        "-X", "-q", "-v", "ON_ERROR_STOP=1",
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $templateDb, "-f", $migration
    )
    $env:PGOPTIONS = "-c search_path=pg_temp,public -c quote_all_identifiers=on"
    Invoke-NativeChecked $psql @(
        "-X", "-q", "-v", "ON_ERROR_STOP=1",
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $templateDb, "-f", $migration
    )
    Remove-Item Env:PGOPTIONS
    Write-Host "PASS fresh apply + hostile exact reapply"

    $drifts = @(
        @{ Name = "column_default"; Sql = "alter table connected_app_private.connections alter column authorization_revision set default 99" },
        @{ Name = "constraint"; Sql = "alter table connected_app_private.connections drop constraint connections_resource_check, add constraint connections_resource_check check (resource = 'mail')" },
        @{ Name = "index"; Sql = "drop index connected_app_private.connected_app_connections_owner_id_idx; create index connected_app_connections_owner_id_idx on connected_app_private.connections(owner_id,id)" },
        @{ Name = "function_source"; Sql = "create or replace function connected_app_private.owner_lock_v1(p_owner_id uuid) returns void language plpgsql security definer set search_path='' as `$fn`$ begin perform 1; end; `$fn`$" },
        @{ Name = "function_config"; Sql = "alter function public.connected_app_get_binding_v1(uuid,uuid) set search_path=public" },
        @{ Name = "table_acl"; Sql = "grant select on connected_app_private.connections to authenticated" },
        @{ Name = "column_acl"; Sql = "grant select(id) on connected_app_private.connections to authenticated" },
        @{ Name = "comment"; Sql = "comment on table connected_app_private.connections is 'DRIFT'" },
        @{ Name = "trigger"; Sql = "alter table public.users disable trigger connected_app_owner_delete_cleanup_v1" },
        @{ Name = "rule"; Sql = "create rule connected_app_drift_rule as on update to connected_app_private.connections do instead nothing" },
        @{ Name = "publication"; Sql = "create publication connected_app_drift_publication for table connected_app_private.connections" },
        @{ Name = "sequence"; Sql = "alter sequence connected_app_private.action_fencing_token_seq increment by 2" },
        @{ Name = "overload"; Sql = "create function public.connected_app_get_binding_v1(uuid) returns jsonb language sql security definer set search_path='' as 'select null::jsonb'" },
        @{ Name = "owner"; Sql = "alter table connected_app_private.connections owner to service_role" },
        @{ Name = "extra_table"; Sql = "create table connected_app_private.drift_table(id integer)" },
        @{ Name = "extra_type"; Sql = "create domain connected_app_private.drift_domain as text" },
        @{ Name = "policy"; Sql = "create policy connected_app_drift_policy on connected_app_private.connections for select to service_role using (true)" },
        @{ Name = "rls"; Sql = "alter table connected_app_private.connections disable row level security" },
        @{ Name = "default_acl"; Sql = "alter default privileges for role postgres in schema connected_app_private grant select on tables to authenticated" }
    )
    foreach ($drift in $drifts) {
        Assert-DriftRefused -Name $drift.Name -Sql $drift.Sql
    }
}
finally {
    Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    foreach ($database in ($created | Select-Object -Unique | Sort-Object -Descending)) {
        & $dropdb -h $HostName -p "$Port" -U $UserName --if-exists $database | Out-Null
    }
}
