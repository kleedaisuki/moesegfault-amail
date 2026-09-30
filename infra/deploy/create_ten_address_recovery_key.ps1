# Create only the versioned repository-level quota recovery key after an admin freeze.
# Do not execute while another operator can rotate/delete this key. GitHub secret PUT
# has no atomic create-only condition; the explicit metadata checks reject known
# existing keys, but the administrative exclusion is still a required contract.
param([Parameter(Mandatory = $true)][string]$Confirm)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repo = 'kleedaisuki/moesegfault-amail'
$name = 'AMAIL_TEN_ADDRESS_RECOVERY_KEY_V1'
if ($Confirm -cne 'CREATE_STAGING_TEN_ADDRESS_RECOVERY_KEY_V1') {
    throw 'ten_address_recovery_key_unconfirmed'
}

# Keep Secret values off argv, files, stdout and diagnostic stderr. gh encrypts
# the value locally for the repository's public key; the value is supplied on stdin.
function Invoke-GhPrivate {
    param([string[]]$Arguments, [string]$InputValue = '')
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = 'gh'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'ten_address_recovery_key_helper_unavailable' }
        $out = $process.StandardOutput.ReadToEndAsync()
        $err = $process.StandardError.ReadToEndAsync()
        if ($InputValue) { $process.StandardInput.Write($InputValue) }
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(60000)) {
            $process.Kill($true)
            throw 'ten_address_recovery_key_helper_unverified'
        }
        return @{ Code = $process.ExitCode; Output = $out.GetAwaiter().GetResult(); Error = $err.GetAwaiter().GetResult() }
    } finally { $process.Dispose() }
}

# Prove exact repository administrative authority before interpreting a Secret 404
# as absence; an inaccessible repository can otherwise be indistinguishable.
$authority = Invoke-GhPrivate -Arguments @('api', "repos/$repo")
if ($authority.Code -ne 0) { throw 'ten_address_recovery_key_authority_unverified' }
try { $metadata = $authority.Output | ConvertFrom-Json } catch { throw 'ten_address_recovery_key_authority_unverified' }
if ($metadata.full_name -cne $repo -or $metadata.permissions.admin -ne $true) {
    throw 'ten_address_recovery_key_authority_unverified'
}

# Idempotency means preserving an existing generation, never silently replacing it.
$prior = Invoke-GhPrivate -Arguments @('api', "repos/$repo/actions/secrets/$name")
if ($prior.Code -eq 0) {
    try { $existing = $prior.Output | ConvertFrom-Json } catch { throw 'ten_address_recovery_key_metadata_unverified' }
    if ($existing.name -cne $name) { throw 'ten_address_recovery_key_metadata_unverified' }
    Write-Output 'ten_address_recovery_key_already_present'
    exit 0
}
try { $missing = $prior.Output | ConvertFrom-Json } catch { throw 'ten_address_recovery_key_metadata_unverified' }
if ($missing.status -cne '404') { throw 'ten_address_recovery_key_metadata_unverified' }

# Domain-separated manifest encryption/candidate derivation use a separate 256-bit
# CSPRNG key, not an Identity password or routing token. Retain generation V1 until
# all corresponding encrypted artifacts have expired AFTER verified exact cleanup.
$bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
$hex = [System.Convert]::ToHexString($bytes).ToLowerInvariant()
try {
    $result = Invoke-GhPrivate -Arguments @('secret', 'set', $name, '--repo', $repo, '--app', 'actions') -InputValue $hex
    if ($result.Code -ne 0) { throw 'ten_address_recovery_key_store_unverified' }
    $readback = Invoke-GhPrivate -Arguments @('api', "repos/$repo/actions/secrets/$name")
    if ($readback.Code -ne 0) { throw 'ten_address_recovery_key_store_unverified' }
    try { $stored = $readback.Output | ConvertFrom-Json } catch { throw 'ten_address_recovery_key_store_unverified' }
    if ($stored.name -cne $name) { throw 'ten_address_recovery_key_store_unverified' }
    Write-Output 'ten_address_recovery_key_created'
} finally {
    [System.Security.Cryptography.CryptographicOperations]::ZeroMemory($bytes)
    $hex = $null
}
