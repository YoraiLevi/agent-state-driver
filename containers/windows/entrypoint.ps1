# Single entry point for the Windows container.
#
#   check   (default) run the credential-free ConPTY host self-test
#   host <workdir> <statedir> [exe] [args...]   run the ConPTY host
#   shell   interactive powershell
#   <anything else>  run verbatim
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\host'

if (-not $Args -or $Args.Count -eq 0) { $Args = @('check') }
$verb = $Args[0]
$rest = @($Args | Select-Object -Skip 1)

switch ($verb) {
    'check' {
        Write-Output ("node:   " + (& node --version))
        Write-Output ("npm:    " + (& npm --version))
        Write-Output ("host:   C:\host")
        Write-Output ""
        & node C:\host\conpty-selftest.js
        exit $LASTEXITCODE
    }
    'host' {
        & node C:\host\conpty-host.js @rest
        exit $LASTEXITCODE
    }
    'shell' {
        & powershell -NoLogo -NoProfile
        exit $LASTEXITCODE
    }
    default {
        & $verb @rest
        exit $LASTEXITCODE
    }
}
