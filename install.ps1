<#
.SYNOPSIS
    One-Click Installer for CATalyst MCP Server (Windows PowerShell 5.1+ / 7+).
.DESCRIPTION
    Pure ASCII wrapper (safe under Windows PowerShell 5.1 regardless of system ANSI code page / BOM):
    1. Locates uv (PATH / ~/.local/bin / ~/.cargo/bin / Scoop).
    2. Creates/syncs the isolated project virtual environment (.venv).
    3. Runs install.py to check 7-Zip (or prompt user choice), discover/prompt CATIA paths,
       build local SQLite DB(s), register the MCP server, and run end-to-end verification.
.EXAMPLE
    .\install.ps1
    powershell -ExecutionPolicy Bypass -File .\install.ps1
    .\install.ps1 --yes
    .\install.ps1 --chm "D:\Dassault\B27\win_b64\code\bin\V5Automation.chm"
    .\install.ps1 --client cursor
#>

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
}
catch {
    # Ignore console encoding errors in non-interactive or redirected hosts
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$prevInstallerProg = $env:CATALYST_INSTALLER_PROG
Push-Location -LiteralPath "$ProjectRoot"

try {
    # 1. Locate uv
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
    if (-not $uvCmd) {
        $uvCandidates = @(
            (Join-Path "$HOME" ".local\bin\uv.exe"),
            (Join-Path "$HOME" ".cargo\bin\uv.exe"),
            (Join-Path "$HOME" "scoop\shims\uv.exe")
        )
        foreach ($cand in $uvCandidates) {
            if (Test-Path -LiteralPath "$cand") {
                $uvCmd = $cand
                break
            }
        }
    }

    if (-not $uvCmd) {
        Write-Host "[ERROR] uv package manager is required but was not found." -ForegroundColor Red
        Write-Host "Install uv first, then re-run .\install.ps1:" -ForegroundColor Yellow
        Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor Cyan
        exit 1
    }

    $installerScript = Join-Path "$ProjectRoot" "install.py"
    $venvPython = Join-Path "$ProjectRoot" ".venv\Scripts\python.exe"
    $env:CATALYST_INSTALLER_PROG = ".\install.ps1"

    # Fast-path: print --help / -h immediately without running uv sync
    $isHelp = ($args -contains "-h") -or ($args -contains "--help")
    if ($isHelp) {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        if (Test-Path -LiteralPath "$venvPython") {
            & "$venvPython" "$installerScript" @args
        }
        else {
            & "$uvCmd" run --no-project python "$installerScript" @args
        }
        $helpExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEap
        exit $helpExit
    }

    # 2. Sync isolated project virtual environment (.venv)
    # Note: Keep ErrorActionPreference=Continue around native CLI invocations so stderr progress
    # output from uv does not trigger terminating NativeCommandError in Windows PowerShell 5.1.
    Write-Host "[STEP 0] Syncing isolated virtual environment (.venv)..." -ForegroundColor Cyan
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & "$uvCmd" sync
    $syncExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap

    if ($syncExit -ne 0) {
        if (Test-Path -LiteralPath "$venvPython") {
            Write-Host "[WARN] uv sync exited with code $syncExit; continuing with existing .venv..." -ForegroundColor Yellow
        }
        else {
            Write-Host "[ERROR] uv sync failed (code $syncExit) and no local .venv exists. Check network or Python 3.10+." -ForegroundColor Red
            exit $syncExit
        }
    }

    # 3. Run Python installer inside isolated .venv
    $ErrorActionPreference = "Continue"
    & "$uvCmd" run python "$installerScript" @args
    $installExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    exit $installExit
}
finally {
    if ($null -eq $prevInstallerProg) {
        Remove-Item Env:CATALYST_INSTALLER_PROG -ErrorAction SilentlyContinue
    }
    else {
        $env:CATALYST_INSTALLER_PROG = $prevInstallerProg
    }
    Pop-Location
}
