param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 55449,
    [string]$UserName = "postgres",
    [string]$Password = "postgres",
    [string]$PgBin = "",
    [string]$PredecessorDatabase = ""
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
$migration = Join-Path $repoRoot (
    "migrations\20261108068900_connected_multi_account_authority.sql"
)
$behavior = Join-Path $repoRoot (
    "tests\postgres\test_connected_multi_account_authority.sql"
)
$races = Join-Path $repoRoot (
    "tests\postgres\test_connected_multi_account_authority_races.sql"
)
$baseline = Join-Path $repoRoot "tests\postgres\connected_app_full_stack_baseline.sql"
$predecessorMigrations = @(
    "20261107190000_connected_app_control_plane.sql",
    "20261107230000_connected_app_secret_payload_stores.sql",
    "20261107231500_connected_app_oauth_secret_custody.sql",
    "20261107233000_connected_app_encrypted_read_results.sql",
    "20261108020000_connected_chat_turn_binding.sql",
    "20261108023000_connected_plan_once.sql",
    "20261108040000_connected_operator_chat_completion.sql",
    "20261108043000_connected_dispatch_execution_outbox.sql",
    "20261108050000_connected_oauth_runtime_authority.sql",
    "20261108052000_connected_chat_action_stage.sql",
    "20261108054000_account_lifecycle_connected_owner_lock.sql",
    "20261108058000_connected_runtime_ledger_binding.sql",
    "20261108061000_connected_grant_cleanup_refresh_fence.sql",
    "20261108062000_connected_owner_read_result_surface.sql",
    "20261108063000_connected_schedule_template_completion.sql",
    "20261108064000_connected_oauth_operator_bridge.sql",
    "20261108065000_connected_external_reconciliation_worker.sql",
    "20261108066000_connected_schedule_occurrence_approval.sql",
    "20261108067000_connected_multi_step_operator_loop.sql",
    "20261108068000_connected_calendar_cancel_snapshot_authority.sql",
    "20261108068500_connected_multi_step_continuation_queue.sql",
    "20261108068600_connected_ciphertext_retention.sql",
    "20261108068700_connected_oauth_callback_owner_binding.sql",
    "20261108068800_connected_oauth_code_custody.sql"
)
$env:PGPASSWORD = $Password
$suffix = "{0:x}" -f $PID
$targetDb = "connected_multi_689_target_$suffix"
$created = [System.Collections.Generic.List[string]]::new()

function Invoke-NativeChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "native command failed: $Executable $($Arguments -join ' ')"
    }
}

function New-TestDatabase {
    param([string]$Database, [string]$Template = "")
    $arguments = @("-h", $HostName, "-p", "$Port", "-U", $UserName)
    if ($Template) { $arguments += @("--template", $Template) }
    $arguments += $Database
    Invoke-NativeChecked $createdb $arguments
    $created.Add($Database)
}

function Invoke-Sql {
    param([string]$Database, [string]$Sql)
    Invoke-NativeChecked $psql @(
        "-X", "-q", "-v", "ON_ERROR_STOP=1",
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $Database, "-c", $Sql
    )
}

function Invoke-File {
    param([string]$Database, [string]$Path, [bool]$Hostile = $false)
    if ($Hostile) {
        $env:PGOPTIONS = "-c search_path=pg_temp,public -c quote_all_identifiers=on"
    }
    try {
        Invoke-NativeChecked $psql @(
            "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $Database, "-f", $Path
        )
    }
    finally {
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    }
}

function Get-SchemaDigest {
    param([string]$Database)
    $dump = & $pgdump @(
        "--schema-only",
        "-h", $HostName, "-p", "$Port", "-U", $UserName, $Database
    ) 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed for $Database" }
    $stableDump = (($dump -split "`r?`n") |
        Where-Object { $_ -notmatch '^\\(un)?restrict\s' }) -join "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($stableDump)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $digest = $hasher.ComputeHash($bytes) }
    finally { $hasher.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace("-", "")
}

function Assert-RefusalNoRepair {
    param(
        [string]$Name,
        [string]$Template,
        [string]$Mutation = ""
    )
    $database = "connected_multi_689_${Name}_$suffix"
    if ($database.Length -gt 63) { throw "database name is too long: $database" }
    New-TestDatabase $database $Template
    if ($Mutation) { Invoke-Sql $database $Mutation }
    $before = Get-SchemaDigest $database
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $env:PGOPTIONS = "-c search_path=pg_temp,public -c quote_all_identifiers=on"
        $output = & $psql @(
            "-X", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $database, "-f", $migration
        ) 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
    }
    finally {
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -eq 0) { throw "drift unexpectedly applied: $Name" }
    if ($output -notmatch "55000") {
        throw "drift did not fail with SQLSTATE 55000: $Name`n$output"
    }
    $after = Get-SchemaDigest $database
    if ($before -ne $after) { throw "drift was mutated before refusal: $Name" }
    Write-Host "PASS SQLSTATE 55000 refusal/no repair: $Name"
}

try {
    $predecessorDb = $PredecessorDatabase
    if (-not $predecessorDb) {
        $predecessorDb = "connected_multi_689_base_$suffix"
        New-TestDatabase $predecessorDb
        Invoke-NativeChecked $psql @(
            "-X", "-q", "-v", "ON_ERROR_STOP=1", "-v", "connected_stack_skip=1",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $predecessorDb, "-f", $baseline
        )
        foreach ($migrationName in $predecessorMigrations) {
            Invoke-File $predecessorDb (Join-Path $repoRoot "migrations\$migrationName")
        }
        Write-Host "PASS fresh exact repository stack through 688"
    }
    New-TestDatabase $targetDb $predecessorDb
    $predecessor = & $psql @(
        "-X", "-At", "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $targetDb, "-c",
        "select connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()"
    )
    if ($LASTEXITCODE -ne 0 -or $predecessor -ne "5e4480837c5ebb316da85be988a6561f") {
        throw "predecessor database is not exact 688 target: $predecessor"
    }

    Invoke-File $targetDb $migration
    $before = Get-SchemaDigest $targetDb
    Invoke-File $targetDb $migration $true
    $after = Get-SchemaDigest $targetDb
    if ($before -ne $after) { throw "hostile exact reapply changed schema state" }
    Write-Host "PASS PostgreSQL 17 first apply + hostile exact reapply"

    Invoke-File $targetDb $behavior
    Invoke-File $targetDb $races
    $target = & $psql @(
        "-X", "-At", "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $targetDb, "-c",
        "select connected_multi_account_private.multi_account_target_fingerprint_v1()"
    )
    if ($LASTEXITCODE -ne 0 -or $target -ne "bf14a3339a25e4e2cdab12ef18523599") {
        throw "multi-account target fingerprint drifted: $target"
    }
    Write-Host "PASS behavior, deletion, both-winner races, and exact target"

    Assert-RefusalNoRepair "missing" ""
    Assert-RefusalNoRepair "partial" $predecessorDb @"
create schema connected_multi_account_private authorization postgres
"@
    Assert-RefusalNoRepair "predecessor" $predecessorDb @"
comment on table connected_oauth_code_private.authorization_code_custody is 'DRIFT'
"@
    Assert-RefusalNoRepair "search_path" $targetDb @"
alter function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) set search_path=public
"@
    Assert-RefusalNoRepair "acl" $targetDb @"
grant execute on function public.connected_app_oauth_finalize_v2(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,bigint,text,text,text,text,text,text,
  uuid,text,timestamptz,timestamptz,text,uuid,text,uuid,text
) to authenticated
"@
    Assert-RefusalNoRepair "owner" $targetDb @"
alter function public.connected_app_operator_prepare_oauth_start_v2(
  uuid,uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text[],text,text,
  timestamptz,timestamptz
) owner to service_role
"@
    Assert-RefusalNoRepair "rls" $targetDb @"
alter table connected_app_private.connections disable row level security
"@
    Assert-RefusalNoRepair "column_acl" $targetDb @"
grant select(code_ciphertext)
on connected_oauth_code_private.authorization_code_custody to service_role
"@
    Assert-RefusalNoRepair "hidden_policy" $targetDb @"
create policy connected_multi_689_hidden_policy
on connected_app_private.connections for select to service_role using (true)
"@
    Assert-RefusalNoRepair "publication" $targetDb @"
create publication connected_multi_689_drift_pub
for table connected_app_private.connections
"@
    Assert-RefusalNoRepair "carried_publication_namespace" $targetDb @"
create publication connected_multi_689_code_schema_drift
for tables in schema connected_oauth_code_private
"@
    Assert-RefusalNoRepair "hidden_trigger" $targetDb @"
create function connected_app_private.connected_multi_689_drift_trigger_v1()
returns trigger language plpgsql set search_path=''
as `$fn`$ begin return new; end; `$fn`$;
create trigger connected_multi_689_hidden_drift before insert
on connected_app_private.connections for each row
execute function connected_app_private.connected_multi_689_drift_trigger_v1()
"@
    Assert-RefusalNoRepair "hidden_rule" $targetDb @"
create rule connected_multi_689_hidden_drift as
on update to connected_app_private.connections do instead nothing
"@
    Assert-RefusalNoRepair "carried_attestation" $targetDb @"
comment on table connected_oauth_code_private.release_bootstrap_dedicated_attestations
is 'DRIFT'
"@
}
finally {
    Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    $cleanupKinds = @(
        "target",
        "base",
        "missing",
        "partial",
        "predecessor",
        "search_path",
        "acl",
        "owner",
        "rls",
        "column_acl",
        "hidden_policy",
        "publication",
        "carried_publication_namespace",
        "hidden_trigger",
        "hidden_rule",
        "carried_attestation"
    )
    $cleanupKindPattern = ($cleanupKinds | ForEach-Object {
        [Regex]::Escape($_)
    }) -join "|"
    $cleanupNamePattern = "^connected_multi_689_($cleanupKindPattern)_$([Regex]::Escape($suffix))`$"
    $cleanupFailures = [System.Collections.Generic.List[string]]::new()

    foreach ($database in ($created | Select-Object -Unique | Sort-Object -Descending)) {
        if ($database -notmatch $cleanupNamePattern) {
            $cleanupFailures.Add("refused unexpected disposable database name: $database")
            continue
        }
        & $dropdb -h $HostName -p "$Port" -U $UserName --if-exists --force $database |
            Out-Null
        if ($LASTEXITCODE -ne 0) {
            $cleanupFailures.Add("dropdb failed for disposable database: $database")
        }
    }

    $cleanupVerificationSql =
        "select pg_catalog.count(*) from pg_catalog.pg_database " +
        "where datname ~ '$cleanupNamePattern'"
    $remaining = & $psql @(
        "-X", "-At", "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", "postgres", "-c",
        $cleanupVerificationSql
    )
    if ($LASTEXITCODE -ne 0) {
        $cleanupFailures.Add("failed to verify disposable database cleanup")
    }
    elseif ($remaining -ne "0") {
        $cleanupFailures.Add(
            "disposable database cleanup left $remaining database(s)"
        )
    }

    if ($cleanupFailures.Count -gt 0) {
        throw ($cleanupFailures -join "; ")
    }
}
