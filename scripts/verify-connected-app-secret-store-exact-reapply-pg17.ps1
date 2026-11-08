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
    $PgBin = (Resolve-Path (
        Join-Path $repoRoot "..\local-pg17-test-20261022\runtime\pgsql\bin"
    )).Path
}
$psql = Join-Path $PgBin "psql.exe"
$createdb = Join-Path $PgBin "createdb.exe"
$dropdb = Join-Path $PgBin "dropdb.exe"
$pgdump = Join-Path $PgBin "pg_dump.exe"
$baseline = Join-Path $repoRoot "tests\postgres\connected_app_full_stack_baseline.sql"
$baseMigration = Join-Path $repoRoot "migrations\20261107190000_connected_app_control_plane.sql"
$storeMigration = Join-Path $repoRoot "migrations\20261107230000_connected_app_secret_payload_stores.sql"
$oauthMigration = Join-Path $repoRoot "migrations\20261107231500_connected_app_oauth_secret_custody.sql"
$env:PGPASSWORD = $Password
$suffix = "{0:x}" -f $PID
$templateDb = "connected_secret_exact_$suffix"
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

function Invoke-Migration {
    param([string]$Database, [string]$Migration, [bool]$Hostile = $false)
    if ($Hostile) {
        $env:PGOPTIONS = "-c search_path=pg_temp,public -c quote_all_identifiers=on"
    }
    try {
        Invoke-NativeChecked $psql @(
            "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $Database, "-f", $Migration
        )
    }
    finally {
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    }
}

function Get-SchemaDigest {
    param([string]$Database)
    $dump = & $pgdump @(
        "--schema-only", "--schema=connected_app_private", "--schema=public",
        "-h", $HostName, "-p", "$Port", "-U", $UserName, $Database
    ) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed for $Database" }
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
    param(
        [string]$Name,
        [string]$Migration,
        [string]$Sql
    )
    $database = "connected_secret_${Name}_$suffix"
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
        $env:PGOPTIONS = "-c search_path=pg_temp,public -c quote_all_identifiers=on"
        $output = & $psql @(
            "-X", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $database, "-f", $Migration
        ) 2>&1 | Out-String
        $psqlExitCode = $LASTEXITCODE
    }
    finally {
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($psqlExitCode -eq 0) { throw "drift unexpectedly reapplied: $Name" }
    if ($output -notmatch "55000" -or $output -notmatch "refusing repair") {
        throw "drift did not fail with exact refusal contract: $Name`n$output"
    }
    $after = Get-SchemaDigest $database
    if ($before -ne $after) { throw "drift was mutated before refusal: $Name" }
    Write-Host "PASS drift refusal/no-repair: $Name"
}

try {
    & $dropdb -h $HostName -p "$Port" -U $UserName --if-exists $templateDb |
        Out-Null
    Invoke-NativeChecked $createdb @(
        "-h", $HostName, "-p", "$Port", "-U", $UserName, $templateDb
    )
    $created.Add($templateDb)
    Invoke-NativeChecked $psql @(
        "-X", "-q", "-v", "ON_ERROR_STOP=1", "-v", "connected_stack_skip=1",
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $templateDb, "-f", $baseline
    )
    Invoke-Migration $templateDb $baseMigration

    Invoke-Migration $templateDb $storeMigration
    $beforeStore = Get-SchemaDigest $templateDb
    Invoke-Migration $templateDb $storeMigration $true
    $afterStore = Get-SchemaDigest $templateDb
    if ($beforeStore -ne $afterStore) {
        throw "encrypted-store exact reapply changed schema state"
    }
    Write-Host "PASS encrypted-store fresh apply + hostile exact reapply"

    Invoke-Migration $templateDb $oauthMigration
    $beforeOAuth = Get-SchemaDigest $templateDb
    Invoke-Migration $templateDb $oauthMigration $true
    $afterOAuth = Get-SchemaDigest $templateDb
    if ($beforeOAuth -ne $afterOAuth) {
        throw "OAuth-secret exact reapply changed schema state"
    }
    Write-Host "PASS OAuth-secret fresh apply + hostile exact reapply"

    $storeDrifts = @(
        @{ Name = "s_col"; Sql = "alter table connected_app_private.payload_envelopes alter column created_at set default pg_catalog.clock_timestamp()" },
        @{ Name = "s_constraint"; Sql = "alter table connected_app_private.payload_envelopes rename constraint connected_payload_lifetime to connected_payload_lifetime_drift" },
        @{ Name = "s_index"; Sql = "drop index connected_app_private.connected_payload_expiry_idx; create index connected_payload_expiry_idx on connected_app_private.payload_envelopes(owner_id,payload_id)" },
        @{ Name = "s_func_src"; Sql = @'
create or replace function connected_app_private.payload_tombstone_before_delete_v1()
returns trigger language plpgsql security definer set search_path=''
as $fn$ begin return old; end; $fn$
'@ },
        @{ Name = "s_func_cfg"; Sql = "alter function public.connected_app_payload_read_v1(uuid,text) set search_path=public" },
        @{ Name = "s_table_acl"; Sql = "grant select on connected_app_private.payload_envelopes to authenticated" },
        @{ Name = "s_column_acl"; Sql = "grant select(payload_id) on connected_app_private.payload_envelopes to authenticated" },
        @{ Name = "s_schema_acl"; Sql = "grant create on schema connected_app_private to authenticated" },
        @{ Name = "s_comment"; Sql = "comment on table connected_app_private.payload_envelopes is 'DRIFT'" },
        @{ Name = "s_trigger"; Sql = "alter table connected_app_private.payload_envelopes disable trigger connected_payload_tombstone_before_delete_v1" },
        @{ Name = "s_hidden_trg"; Sql = @'
create function connected_app_private.store_drift_trigger_v1()
returns trigger language plpgsql set search_path='' as $fn$ begin return new; end; $fn$;
create trigger connected_store_hidden_drift before insert
on connected_app_private.payload_envelopes for each row
execute function connected_app_private.store_drift_trigger_v1()
'@ },
        @{ Name = "s_rule"; Sql = "create rule connected_store_drift_rule as on update to connected_app_private.payload_envelopes do instead nothing" },
        @{ Name = "s_policy"; Sql = "create policy connected_store_drift_policy on connected_app_private.payload_envelopes for select to service_role using (true)" },
        @{ Name = "s_pub"; Sql = "create publication connected_store_drift_pub for table connected_app_private.payload_envelopes" },
        @{ Name = "s_overload"; Sql = "create function public.connected_app_payload_read_v1(uuid) returns jsonb language sql security definer set search_path='' as 'select null::jsonb'" },
        @{ Name = "s_owner"; Sql = "alter table connected_app_private.payload_envelopes owner to service_role" },
        @{ Name = "s_rls"; Sql = "alter table connected_app_private.payload_envelopes disable row level security" },
        @{ Name = "s_default_acl"; Sql = "alter default privileges for role postgres in schema connected_app_private grant select on tables to authenticated" }
    )
    foreach ($drift in $storeDrifts) {
        Assert-DriftRefused $drift.Name $storeMigration $drift.Sql
    }

    $oauthDrifts = @(
        @{ Name = "o_col"; Sql = "alter table connected_app_private.oauth_secret_custody alter column accepted_at set default pg_catalog.statement_timestamp()" },
        @{ Name = "o_constraint"; Sql = "alter table connected_app_private.oauth_secret_custody rename constraint connected_oauth_secret_lifetime to connected_oauth_secret_lifetime_drift" },
        @{ Name = "o_index"; Sql = "drop index connected_app_private.connected_oauth_secret_expiry_idx; create index connected_oauth_secret_expiry_idx on connected_app_private.oauth_secret_custody(owner_id,flow_id)" },
        @{ Name = "o_func_src"; Sql = @'
create or replace function connected_app_private.oauth_secret_tombstone_before_delete_v1()
returns trigger language plpgsql security definer set search_path=''
as $fn$ begin return old; end; $fn$
'@ },
        @{ Name = "o_func_cfg"; Sql = "alter function connected_app_private.oauth_secret_tombstone_before_delete_v1() set search_path=public" },
        @{ Name = "o_table_acl"; Sql = "grant select on connected_app_private.oauth_secret_custody to authenticated" },
        @{ Name = "o_column_acl"; Sql = "grant select(flow_id) on connected_app_private.oauth_secret_custody to authenticated" },
        @{ Name = "o_comment"; Sql = "comment on table connected_app_private.oauth_secret_custody is 'DRIFT'" },
        @{ Name = "o_trigger"; Sql = "alter table connected_app_private.oauth_secret_custody disable trigger connected_oauth_secret_tombstone_before_delete" },
        @{ Name = "o_hidden_trg"; Sql = @'
create function connected_app_private.oauth_drift_trigger_v1()
returns trigger language plpgsql set search_path='' as $fn$ begin return new; end; $fn$;
create trigger connected_oauth_hidden_drift before insert
on connected_app_private.oauth_secret_custody for each row
execute function connected_app_private.oauth_drift_trigger_v1()
'@ },
        @{ Name = "o_rule"; Sql = "create rule connected_oauth_drift_rule as on update to connected_app_private.oauth_secret_custody do instead nothing" },
        @{ Name = "o_policy"; Sql = "create policy connected_oauth_drift_policy on connected_app_private.oauth_secret_custody for select to service_role using (true)" },
        @{ Name = "o_pub"; Sql = "create publication connected_oauth_drift_pub for table connected_app_private.oauth_secret_custody" },
        @{ Name = "o_overload"; Sql = "create function public.connected_app_oauth_secret_abort_v1(uuid) returns jsonb language sql security definer set search_path='' as 'select null::jsonb'" },
        @{ Name = "o_owner"; Sql = "alter table connected_app_private.oauth_secret_custody owner to service_role" },
        @{ Name = "o_rls"; Sql = "alter table connected_app_private.oauth_secret_custody disable row level security" }
    )
    foreach ($drift in $oauthDrifts) {
        Assert-DriftRefused $drift.Name $oauthMigration $drift.Sql
    }
}
finally {
    Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    foreach ($database in ($created | Select-Object -Unique | Sort-Object -Descending)) {
        & $dropdb -h $HostName -p "$Port" -U $UserName --if-exists $database |
            Out-Null
    }
}
