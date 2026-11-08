param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 5432,
    [string]$UserName = "postgres",
    [string]$Password = "postgres",
    [string]$PgBin = "",
    [string]$ExpectedFinalTarget = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PGPASSWORD = $Password
$suffix = "{0:x8}" -f $PID
$databasePrefix = "connected_operator_ci_"
$created = [System.Collections.Generic.List[string]]::new()
$createdApiRoles = $false

function Resolve-PgTool {
    param([Parameter(Mandatory = $true)][string]$Name)
    if ($PgBin) {
        foreach ($leaf in @($Name, "$Name.exe")) {
            $candidate = Join-Path $PgBin $leaf
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        }
        throw "PostgreSQL tool is absent from PgBin: $Name"
    }
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    }
    if ($null -eq $command) { throw "PostgreSQL tool is unavailable: $Name" }
    return $command.Source
}

$psql = Resolve-PgTool "psql"
$createdb = Resolve-PgTool "createdb"
$dropdb = Resolve-PgTool "dropdb"
$pgdump = Resolve-PgTool "pg_dump"

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        $safeArguments = @(
            $Arguments | ForEach-Object {
                if ($_ -match '^connected_test_password=') {
                    'connected_test_password=<redacted>'
                }
                else { $_ }
            }
        )
        throw "native command failed: $Executable $($safeArguments -join ' ')"
    }
}

function Assert-DatabaseName {
    param([Parameter(Mandatory = $true)][string]$Database)
    $escapedSuffix = [Regex]::Escape($suffix)
    if (
        $Database.Length -gt 63 -or
        $Database -notmatch "^$databasePrefix[a-z0-9_]+_$escapedSuffix`$"
    ) {
        throw "refused unsafe disposable database name: $Database"
    }
}

function New-TestDatabase {
    param(
        [Parameter(Mandatory = $true)][string]$Database,
        [string]$Template = ""
    )
    Assert-DatabaseName $Database
    $arguments = @(
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "--maintenance-db", "postgres"
    )
    if ($Template) {
        Assert-DatabaseName $Template
        $arguments += @("--template", $Template)
    }
    $arguments += $Database
    Invoke-NativeChecked $createdb $arguments
    $created.Add($Database)
}

function Remove-TestDatabase {
    param([Parameter(Mandatory = $true)][string]$Database)
    Assert-DatabaseName $Database
    & $dropdb -h $HostName -p "$Port" -U $UserName `
        --maintenance-db postgres --if-exists --force $Database | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "dropdb failed: $Database" }
    [void]$created.Remove($Database)
}

function Invoke-Sql {
    param(
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$Sql
    )
    Assert-DatabaseName $Database
    Invoke-NativeChecked $psql @(
        "-X", "-q", "-v", "ON_ERROR_STOP=1",
        "-h", $HostName, "-p", "$Port", "-U", $UserName,
        "-d", $Database, "-c", $Sql
    )
}

function Invoke-File {
    param(
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$Path,
        [bool]$Hostile = $false,
        [string[]]$Variables = @()
    )
    Assert-DatabaseName $Database
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "SQL file is absent: $Path"
    }
    if ($Hostile) {
        $hostileOptions = "-c search_path=pg_temp,public"
        # Older reviewed migrations predate quote-sensitive catalog manifests.
        # Every migration still receives a hostile search_path reapply. Enable
        # quote_all_identifiers only when the migration explicitly normalizes
        # it before computing its own exact-target fingerprint.
        $source = Get-Content -LiteralPath $Path -Raw
        if ($source -match "(?i)quote_all_identifiers[^\r\n]*off") {
            $hostileOptions += " -c quote_all_identifiers=on"
        }
        $env:PGOPTIONS = $hostileOptions
    }
    try {
        $arguments = @(
            "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-h", $HostName, "-p", "$Port", "-U", $UserName,
            "-d", $Database
        )
        foreach ($variable in $Variables) { $arguments += @("-v", $variable) }
        $arguments += @("-f", $Path)
        Invoke-NativeChecked $psql $arguments
    }
    finally {
        Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    }
}

function Get-Scalar {
    param(
        [Parameter(Mandatory = $true)][string]$Database,
        [Parameter(Mandatory = $true)][string]$Sql
    )
    Assert-DatabaseName $Database
    $value = & $psql -X -qAt -v ON_ERROR_STOP=1 `
        -h $HostName -p "$Port" -U $UserName -d $Database -c $Sql
    if ($LASTEXITCODE -ne 0) { throw "scalar query failed: $Sql" }
    return ($value | Out-String).Trim()
}

function Get-SchemaDigest {
    param([Parameter(Mandatory = $true)][string]$Database)
    Assert-DatabaseName $Database
    $dump = & $pgdump --schema-only `
        -h $HostName -p "$Port" -U $UserName $Database 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed: $Database" }
    $stable = (($dump -split "`r?`n") | Where-Object {
        $_ -notmatch '^\\(un)?restrict\s'
    }) -join "`n"
    $bytes = [Text.Encoding]::UTF8.GetBytes($stable)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $digest = $hasher.ComputeHash($bytes) }
    finally { $hasher.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace("-", "")
}

function Invoke-StageGate {
    param(
        [Parameter(Mandatory = $true)][string]$StageDatabase,
        [Parameter(Mandatory = $true)][string]$Stage,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$SqlFiles
    )
    $index = 0
    foreach ($relative in $SqlFiles) {
        $index += 1
        $testDatabase = "$databasePrefix${Stage}_test_${index}_$suffix"
        New-TestDatabase $testDatabase $StageDatabase
        try {
            # The current-main substrate includes fixed synthetic cohort rows
            # whose UUIDs predate and collide with several connected behavior
            # fixtures. Behavior clones validate the connected stage itself,
            # so remove only account-scoped fixture data before each SQL gate.
            Invoke-Sql $testDatabase "delete from public.users"
            # Several original connected behavior fixtures predate the current
            # registration-cohort trigger and intentionally insert only a user
            # UUID. Keep that unrelated production trigger active while giving
            # those disposable inserts an explicit non-production environment.
            Invoke-Sql $testDatabase (
                "alter table public.users " +
                "alter column registration_environment " +
                "set default 'development', " +
                "alter column created_at " +
                "set default pg_catalog.clock_timestamp(); " +
                "alter table public.sessions " +
                "alter column token_hash " +
                "set default pg_catalog.gen_random_uuid()::text"
            )
            Invoke-File $testDatabase (Join-Path $repoRoot $relative) $false @(
                "connected_test_host=$HostName",
                "connected_test_port=$Port",
                "connected_test_user=$UserName",
                "connected_test_password=$Password",
                "connected_test_database=$testDatabase"
            )
        }
        finally {
            Remove-TestDatabase $testDatabase
        }
    }
    if ($SqlFiles.Count -gt 0) {
        Write-Host "PASS $Stage behavior/race gates ($($SqlFiles.Count))"
    }
}

function Assert-RefusalNoRepair {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Template,
        [Parameter(Mandatory = $true)][string]$Migration,
        [Parameter(Mandatory = $true)][string]$Mutation
    )
    $database = "$databasePrefix${Name}_$suffix"
    New-TestDatabase $database $Template
    try {
        Invoke-Sql $database $Mutation
        $before = Get-SchemaDigest $database
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $env:PGOPTIONS = (
                "-c search_path=pg_temp,public " +
                "-c quote_all_identifiers=on"
            )
            $output = & $psql -X -v ON_ERROR_STOP=1 -v VERBOSITY=verbose `
                -h $HostName -p "$Port" -U $UserName -d $database `
                -f $Migration 2>&1 | Out-String
            $exitCode = $LASTEXITCODE
        }
        finally {
            Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
            $ErrorActionPreference = $previousPreference
        }
        if ($exitCode -eq 0) { throw "drift unexpectedly applied: $Name" }
        if ($output -notmatch "55000") {
            throw "drift did not fail with SQLSTATE 55000: $Name`n$output"
        }
        $after = Get-SchemaDigest $database
        if ($before -ne $after) { throw "drift was repaired or mutated: $Name" }
        Write-Host "PASS SQLSTATE 55000 refusal/no repair: $Name"
    }
    finally {
        Remove-TestDatabase $database
    }
}

$stages = @(
    @{
        Id = "190"; Migration = "migrations/20261107190000_connected_app_control_plane.sql";
        Tests = @(
            "tests/postgres/test_connected_app_operator_control_plane.sql",
            "tests/postgres/test_connected_app_action_preparation.sql",
            "scripts/verify-connected-app-action-preparation-races-pg17.sql"
        )
    },
    @{
        Id = "230"; Migration = "migrations/20261107230000_connected_app_secret_payload_stores.sql";
        Tests = @(
            "scripts/verify-connected-app-durable-stores-pg17.sql",
            "scripts/verify-connected-app-durable-stores-races-pg17.sql",
            "scripts/verify-connected-app-credential-revoke-races-pg17.sql"
        )
    },
    @{
        Id = "231"; Migration = "migrations/20261107231500_connected_app_oauth_secret_custody.sql";
        Tests = @(
            "scripts/verify-connected-app-oauth-secret-custody-pg17.sql",
            "scripts/verify-connected-app-oauth-secret-custody-races-pg17.sql"
        )
    },
    @{
        Id = "233"; Migration = "migrations/20261107233000_connected_app_encrypted_read_results.sql";
        Tests = @("scripts/verify-connected-app-read-results-pg17.sql")
    },
    @{ Id = "200"; Migration = "migrations/20261108020000_connected_chat_turn_binding.sql"; Tests = @() },
    @{
        Id = "230p"; Migration = "migrations/20261108023000_connected_plan_once.sql";
        Tests = @(
            "tests/postgres/test_connected_plan_once.sql",
            "scripts/verify-connected-plan-once-races-pg17.sql"
        )
    },
    @{
        Id = "400"; Migration = "migrations/20261108040000_connected_operator_chat_completion.sql";
        Tests = @(
            "tests/postgres/test_connected_operator_chat_completion.sql",
            "scripts/verify-connected-operator-chat-completion-races-pg17.sql"
        )
    },
    @{ Id = "430"; Migration = "migrations/20261108043000_connected_dispatch_execution_outbox.sql"; Tests = @() },
    @{
        Id = "500"; Migration = "migrations/20261108050000_connected_oauth_runtime_authority.sql";
        Tests = @("tests/postgres/test_connected_oauth_runtime_authority.sql")
    },
    @{
        Id = "520"; Migration = "migrations/20261108052000_connected_chat_action_stage.sql";
        Tests = @("tests/postgres/test_connected_chat_action_stage.sql")
    },
    @{
        Id = "540"; Migration = "migrations/20261108054000_account_lifecycle_connected_owner_lock.sql";
        Tests = @(
            "tests/postgres/test_account_lifecycle_connected_owner_lock.sql",
            "tests/postgres/test_account_lifecycle_connected_writer_races.sql"
        )
    },
    @{
        Id = "580"; Migration = "migrations/20261108058000_connected_runtime_ledger_binding.sql";
        Tests = @("tests/postgres/test_connected_runtime_ledger_binding.sql")
    },
    @{
        Id = "610"; Migration = "migrations/20261108061000_connected_grant_cleanup_refresh_fence.sql";
        Tests = @(
            "tests/postgres/test_connected_grant_cleanup_refresh_fence.sql",
            "scripts/verify-connected-grant-cleanup-refresh-races-pg17.sql"
        )
    },
    @{
        Id = "620"; Migration = "migrations/20261108062000_connected_owner_read_result_surface.sql";
        Tests = @("tests/postgres/test_connected_owner_read_result_surface.sql")
    },
    @{
        Id = "630"; Migration = "migrations/20261108063000_connected_schedule_template_completion.sql";
        Tests = @(
            "tests/postgres/test_connected_schedule_template_completion.sql",
            "tests/postgres/test_connected_schedule_template_races.sql"
        )
    },
    @{
        Id = "640"; Migration = "migrations/20261108064000_connected_oauth_operator_bridge.sql";
        Tests = @("tests/postgres/test_connected_oauth_operator_bridge.sql")
    },
    @{
        Id = "650"; Migration = "migrations/20261108065000_connected_external_reconciliation_worker.sql";
        Tests = @(
            "tests/postgres/test_connected_external_reconciliation_worker.sql",
            "scripts/verify-connected-external-reconciliation-races-pg17.sql"
        )
    },
    @{
        Id = "660"; Migration = "migrations/20261108066000_connected_schedule_occurrence_approval.sql";
        Tests = @(
            "tests/postgres/test_connected_schedule_occurrence_approval.sql",
            "tests/postgres/test_connected_schedule_occurrence_approval_races.sql"
        )
    },
    @{
        Id = "670"; Migration = "migrations/20261108067000_connected_multi_step_operator_loop.sql";
        Tests = @(
            "tests/postgres/test_connected_multi_step_operator_loop.sql",
            "tests/postgres/test_connected_multi_step_operator_loop_races.sql"
        )
    },
    @{
        Id = "680"; Migration = "migrations/20261108068000_connected_calendar_cancel_snapshot_authority.sql";
        Tests = @(
            "tests/postgres/test_connected_calendar_cancel_snapshot_authority.sql",
            "tests/postgres/test_connected_calendar_cancel_snapshot_races.sql"
        )
    },
    @{
        Id = "685"; Migration = "migrations/20261108068500_connected_multi_step_continuation_queue.sql";
        Tests = @(
            "tests/postgres/test_connected_multi_step_continuation_queue.sql",
            "tests/postgres/test_connected_multi_step_continuation_approval.sql"
        )
    },
    @{
        Id = "686"; Migration = "migrations/20261108068600_connected_ciphertext_retention.sql";
        Tests = @(
            "tests/postgres/test_connected_ciphertext_retention.sql",
            "tests/postgres/test_connected_ciphertext_retention_loop.sql",
            "tests/postgres/test_connected_ciphertext_retention_races.sql"
        )
    },
    @{
        Id = "687"; Migration = "migrations/20261108068700_connected_oauth_callback_owner_binding.sql";
        Tests = @(
            "tests/postgres/test_connected_oauth_callback_owner_binding.sql",
            "tests/postgres/test_connected_oauth_callback_owner_binding_races.sql"
        )
    },
    @{
        Id = "688"; Migration = "migrations/20261108068800_connected_oauth_code_custody.sql";
        Tests = @(
            "tests/postgres/test_connected_oauth_code_custody.sql",
            "tests/postgres/test_connected_oauth_code_custody_races.sql"
        )
    },
    @{
        Id = "689"; Migration = "migrations/20261108068900_connected_multi_account_authority.sql";
        Tests = @(
            "tests/postgres/test_connected_multi_account_authority.sql",
            "tests/postgres/test_connected_multi_account_authority_races.sql"
        )
    },
    @{
        Id = "690"; Migration = "migrations/20261108069000_connected_runtime_readiness_attestation.sql";
        Tests = @("tests/postgres/test_connected_runtime_readiness_attestation.sql")
    },
    @{
        Id = "691"; Migration = "migrations/20261108069100_connected_approval_effect_transition.sql";
        Tests = @(
            "tests/postgres/test_connected_approval_effect_transition.sql",
            "scripts/verify-connected-approval-effect-races-pg17.sql"
        )
    }
)

$targetDatabase = "$databasePrefix" + "target_$suffix"
$pre690Database = "$databasePrefix" + "pre690_$suffix"
$pre691Database = "$databasePrefix" + "pre691_$suffix"

try {
    $expectedVersions = @(
        $stages | ForEach-Object {
            $versionMatch = [Regex]::Match(
                $_.Migration,
                '(?<![0-9])([0-9]{14})_[^/\\]+\.sql$'
            )
            if (-not $versionMatch.Success) {
                throw "migration path does not contain an exact version: $($_.Migration)"
            }
            $versionMatch.Groups[1].Value
        }
    )
    if (
        $expectedVersions.Count -ne 27 -or
        (@($expectedVersions | Select-Object -Unique)).Count -ne 27
    ) {
        throw "connected migration stage map is incomplete or duplicated"
    }
    $hostBootstrap = Get-Content `
        (Join-Path $repoRoot "backend/connected_app_host_bootstrap.py") -Raw
    $manifestMatch = [Regex]::Match(
        $hostBootstrap,
        '"ordered_migrations"\s*:\s*\[(.*?)\]',
        [Text.RegularExpressions.RegexOptions]::Singleline
    )
    if (-not $manifestMatch.Success) {
        throw "connected host ordered_migrations manifest is absent"
    }
    $hostVersions = @(
        [Regex]::Matches($manifestMatch.Groups[1].Value, '"([0-9]{14})"') |
            ForEach-Object { $_.Groups[1].Value }
    )
    if (($hostVersions -join ',') -ne ($expectedVersions -join ',')) {
        throw (
            "connected migration stage map disagrees with host bootstrap: " +
            ($hostVersions -join ',')
        )
    }
    $requiredFinalGates = @{
        "690" = @("tests/postgres/test_connected_runtime_readiness_attestation.sql")
        "691" = @(
            "tests/postgres/test_connected_approval_effect_transition.sql",
            "scripts/verify-connected-approval-effect-races-pg17.sql"
        )
    }
    foreach ($stageId in $requiredFinalGates.Keys) {
        $stage = $stages | Where-Object { $_.Id -eq $stageId }
        if ($null -eq $stage -or
            (($stage.Tests | Sort-Object) -join ',') -ne
            (($requiredFinalGates[$stageId] | Sort-Object) -join ',')) {
            throw "required final behavior/race gate is omitted at stage $stageId"
        }
    }
    foreach ($stage in $stages) {
        $migrationPath = Join-Path $repoRoot $stage.Migration
        if (-not (Test-Path -LiteralPath $migrationPath -PathType Leaf)) {
            throw "mapped migration is absent: $($stage.Migration)"
        }
        foreach ($testPath in $stage.Tests) {
            if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $testPath) -PathType Leaf)) {
                throw "mapped behavior/race gate is absent: $testPath"
            }
        }
    }
    Write-Host "PASS exact 27-migration host manifest and final gate inventory"

    if (-not $ExpectedFinalTarget) {
        $config = Get-Content (Join-Path $repoRoot "backend/config.py") -Raw
        $match = [Regex]::Match(
            $config,
            "CONNECTED_APPS_DATABASE_TARGET_FINGERPRINT\s*=\s*'([0-9a-f]{32})'"
        )
        if (-not $match.Success) { throw "final database target is not pinned" }
        $ExpectedFinalTarget = $match.Groups[1].Value
    }
    if ($ExpectedFinalTarget -notmatch '^[0-9a-f]{32}$') {
        throw "ExpectedFinalTarget is invalid"
    }

    New-TestDatabase $targetDatabase
    $serverVersion = Get-Scalar $targetDatabase "show server_version_num"
    if ($serverVersion -ne "170011") {
        throw "PostgreSQL 17.11 is required; observed server_version_num=$serverVersion"
    }
    Write-Host "PASS exact PostgreSQL server_version_num 170011"

    $apiRoleCount = Get-Scalar $targetDatabase @"
select pg_catalog.count(*)
from pg_catalog.pg_roles
where rolname in ('anon','authenticated','service_role')
"@
    if ($apiRoleCount -eq "0") {
        Invoke-Sql $targetDatabase @'
do $roles$
begin
  create role anon nologin inherit nobypassrls;
  create role authenticated nologin inherit nobypassrls;
  create role service_role nologin inherit nobypassrls;
end;
$roles$
'@
        $createdApiRoles = $true
    }
    elseif ($apiRoleCount -ne "3") {
        throw "connected CI API roles are partially initialized"
    }
    $roleContract = Get-Scalar $targetDatabase @"
select (
  not exists (
    select 1 from pg_catalog.pg_roles
    where rolname='authenticator'
  )
  and not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname in ('anon','authenticated','service_role')
      and (
        rolsuper or not rolinherit or rolcreaterole or rolcreatedb
        or rolcanlogin or rolreplication or rolbypassrls
        or rolconnlimit<>-1 or rolconfig is not null
      )
  )
  and exists (
    select 1 from pg_catalog.pg_roles
    where rolname='postgres' and rolsuper and rolinherit
      and rolcreaterole and rolcreatedb and rolcanlogin
      and rolreplication and rolbypassrls and rolconnlimit=-1
      and rolconfig is null
  )
  and not exists (
    select 1
    from pg_catalog.pg_auth_members membership
    join pg_catalog.pg_roles member_role on member_role.oid=membership.member
    join pg_catalog.pg_roles granted_role on granted_role.oid=membership.roleid
    where member_role.rolname in (
      'postgres','anon','authenticated','service_role'
    ) or granted_role.rolname in (
      'postgres','anon','authenticated','service_role'
    )
  )
)::text
"@
    if ($roleContract -ne "true") {
        throw (
            "connected CI role fixture is not exact; use an isolated " +
            "PostgreSQL 17 cluster instead of mutating shared roles"
        )
    }
    Write-Host "PASS exact non-mutating connected CI role fixture"

    Invoke-File $targetDatabase `
        (Join-Path $repoRoot "tests/postgres/connected_app_full_stack_baseline.sql") `
        $false @("connected_stack_skip=1")

    foreach ($stage in $stages) {
        if ($stage.Id -eq "690") {
            New-TestDatabase $pre690Database $targetDatabase
        }
        if ($stage.Id -eq "691") {
            New-TestDatabase $pre691Database $targetDatabase
        }
        $migration = Join-Path $repoRoot $stage.Migration
        Invoke-File $targetDatabase $migration
        $before = Get-SchemaDigest $targetDatabase
        Invoke-File $targetDatabase $migration $true
        $after = Get-SchemaDigest $targetDatabase
        if ($before -ne $after) {
            throw "hostile exact reapply changed schema: $($stage.Id)"
        }
        Invoke-StageGate $targetDatabase $stage.Id $stage.Tests
        Write-Host "PASS ordered first apply + hostile reapply: $($stage.Id)"
    }

    $target = Get-Scalar $targetDatabase (
        "select connected_readiness_private." +
        "runtime_readiness_target_fingerprint_v1()"
    )
    if ($target -ne $ExpectedFinalTarget) {
        throw "final connected target drifted: $target"
    }
    Write-Host "PASS exact final connected target: $target"

    $migration690 = Join-Path $repoRoot `
        "migrations/20261108069000_connected_runtime_readiness_attestation.sql"
    $migration691 = Join-Path $repoRoot `
        "migrations/20261108069100_connected_approval_effect_transition.sql"

    Assert-RefusalNoRepair "690_predecessor_comment" $pre690Database $migration690 @"
comment on table connected_oauth_code_private.authorization_code_custody is 'DRIFT'
"@
    Assert-RefusalNoRepair "690_target_source" $pre691Database $migration690 @"
create or replace function connected_readiness_private.runtime_readiness_target_fingerprint_v1()
returns text language sql stable security definer set search_path=''
as `$fn`$ select '$((Get-Scalar $pre691Database "select connected_readiness_private.runtime_readiness_target_fingerprint_v1()"))'::text `$fn`$
"@
    Assert-RefusalNoRepair "690_target_acl" $pre691Database $migration690 @"
grant execute on function connected_readiness_private.runtime_readiness_target_fingerprint_v1() to service_role
"@
    Assert-RefusalNoRepair "690_target_owner" $pre691Database $migration690 @"
alter function connected_readiness_private.runtime_readiness_target_fingerprint_v1() owner to service_role
"@
    Assert-RefusalNoRepair "690_target_search_path" $pre691Database $migration690 @"
alter function connected_readiness_private.runtime_readiness_target_fingerprint_v1() set search_path=pg_catalog
"@
    Assert-RefusalNoRepair "690_publication" $pre691Database $migration690 @"
create publication connected_operator_ci_690_drift for table connected_app_private.connections
"@

    $finalTargetLiteral = $ExpectedFinalTarget
    Assert-RefusalNoRepair "691_predecessor_source" $pre691Database $migration691 @"
create or replace function connected_readiness_private.runtime_readiness_target_fingerprint_v1()
returns text language sql stable security definer set search_path=''
as `$fn`$ select '$((Get-Scalar $pre691Database "select connected_readiness_private.runtime_readiness_target_fingerprint_v1()"))'::text `$fn`$
"@
    Assert-RefusalNoRepair "691_predecessor_owner" $pre691Database $migration691 @"
alter function connected_readiness_private.runtime_readiness_target_fingerprint_v1() owner to service_role
"@
    Assert-RefusalNoRepair "691_predecessor_acl" $pre691Database $migration691 @"
grant execute on function connected_readiness_private.runtime_readiness_target_fingerprint_v1() to service_role
"@
    Assert-RefusalNoRepair "691_predecessor_search_path" $pre691Database $migration691 @"
alter function connected_readiness_private.runtime_readiness_target_fingerprint_v1() set search_path=pg_catalog
"@
    foreach ($functionCase in @(
        @{ Alias = "target"; Name = "runtime_readiness_target_fingerprint_v1" },
        @{ Alias = "catalog"; Name = "runtime_readiness_catalog_fingerprint_v1" }
    )) {
        $functionName = $functionCase.Name
        $functionAlias = $functionCase.Alias
        Assert-RefusalNoRepair "691_${functionAlias}_source" $targetDatabase $migration691 @"
create or replace function connected_readiness_private.${functionName}()
returns text language sql stable security definer set search_path=''
as `$fn`$ select '$finalTargetLiteral'::text `$fn`$
"@
        Assert-RefusalNoRepair "691_${functionAlias}_owner" $targetDatabase $migration691 @"
alter function connected_readiness_private.${functionName}() owner to service_role
"@
        Assert-RefusalNoRepair "691_${functionAlias}_acl" $targetDatabase $migration691 @"
grant execute on function connected_readiness_private.${functionName}() to service_role
"@
        Assert-RefusalNoRepair "691_${functionAlias}_path" $targetDatabase $migration691 @"
alter function connected_readiness_private.${functionName}() set search_path=pg_catalog
"@
    }
    Assert-RefusalNoRepair "691_create_approval_acl" $targetDatabase $migration691 @"
grant execute on function public.connected_app_create_approval_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,
  timestamptz,timestamptz
) to service_role
"@
    Assert-RefusalNoRepair "691_consume_approval_acl" $targetDatabase $migration691 @"
grant execute on function public.connected_app_consume_approval_v1(
  uuid,uuid,uuid,uuid,bigint,text
) to service_role
"@
    Assert-RefusalNoRepair "691_begin_effect_acl" $targetDatabase $migration691 @"
grant execute on function public.connected_app_begin_effect_v1(
  uuid,uuid,uuid,bigint,text,uuid,uuid,timestamptz
) to service_role
"@
    Assert-RefusalNoRepair "691_wrapper_comment" $targetDatabase $migration691 @"
comment on function public.connected_app_consume_approval_and_begin_effect_v1(
  uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamptz
) is 'DRIFT'
"@
    Assert-RefusalNoRepair "691_wrapper_overload" $targetDatabase $migration691 @"
create function public.connected_app_consume_approval_and_begin_effect_v1(text)
returns jsonb language sql as `$fn`$ select '{}'::jsonb `$fn`$
"@
    Assert-RefusalNoRepair "691_hidden_trigger" $targetDatabase $migration691 @"
create function connected_app_private.connected_operator_ci_drift_trigger_v1()
returns trigger language plpgsql set search_path=''
as `$fn`$ begin return new; end; `$fn`$;
create trigger connected_operator_ci_hidden_drift before insert
on connected_app_private.connections for each row
execute function connected_app_private.connected_operator_ci_drift_trigger_v1()
"@
    Assert-RefusalNoRepair "691_hidden_rule" $targetDatabase $migration691 @"
create rule connected_operator_ci_hidden_drift as
on update to connected_app_private.connections do instead nothing
"@
    Assert-RefusalNoRepair "691_publication" $targetDatabase $migration691 @"
create publication connected_operator_ci_691_drift for table connected_app_private.connections
"@
    Assert-RefusalNoRepair "691_column_acl" $targetDatabase $migration691 @"
grant select(authorization_snapshot_sha256)
on connected_app_private.connections to service_role
"@
    Assert-RefusalNoRepair "691_hidden_policy" $targetDatabase $migration691 @"
create policy connected_operator_ci_hidden_policy
on connected_app_private.connections for select to service_role using (true)
"@
    Write-Host "PASS final 690/691 SQLSTATE 55000 no-repair matrix"
}
finally {
    Remove-Item Env:PGOPTIONS -ErrorAction SilentlyContinue
    $cleanupErrors = [System.Collections.Generic.List[string]]::new()
    foreach ($database in ($created | Select-Object -Unique | Sort-Object -Descending)) {
        try { Remove-TestDatabase $database }
        catch { $cleanupErrors.Add($_.Exception.Message) }
    }
    if ($createdApiRoles) {
        & $psql -X -q -v ON_ERROR_STOP=1 `
            -h $HostName -p "$Port" -U $UserName -d postgres `
            -c "drop role if exists service_role, authenticated, anon" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $cleanupErrors.Add("failed to remove connected CI role fixture")
        }
    }
    $pattern = "^$databasePrefix[a-z0-9_]+_$([Regex]::Escape($suffix))`$"
    try {
        $remaining = & $psql -X -qAt -v ON_ERROR_STOP=1 `
            -h $HostName -p "$Port" -U $UserName -d postgres `
            -c "select count(*) from pg_catalog.pg_database where datname ~ '$pattern'"
        if ($LASTEXITCODE -ne 0) {
            $cleanupErrors.Add("failed to verify disposable database cleanup")
        }
        elseif (($remaining | Out-String).Trim() -ne "0") {
            $cleanupErrors.Add("disposable database cleanup left database(s)")
        }
    }
    catch { $cleanupErrors.Add($_.Exception.Message) }
    if ($cleanupErrors.Count -gt 0) {
        throw ($cleanupErrors -join "; ")
    }
}
