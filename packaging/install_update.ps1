param([Parameter(Mandatory=$true)][string]$Manifest)
$ErrorActionPreference = 'Stop'
$stage = [IO.Path]::GetFullPath((Split-Path -Parent $Manifest))
$log = Join-Path $stage 'install.log'
$names = @('Sortrr.exe', '_internal', 'licenses', 'Read me.txt', 'version.json')
$backed = @()
$installed = @()
$locked = $false
$mutex = $null
try {
    $plan = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
    $target = [IO.Path]::GetFullPath($plan.install).TrimEnd('\')
    $package = [IO.Path]::GetFullPath($plan.package)
    $parent = [IO.Path]::GetDirectoryName($target)
    if ([IO.Path]::GetDirectoryName($stage) -ne $parent -or
        [IO.Path]::GetFileName($stage) -notlike '.sortrr-update-*' -or
        $package -ne (Join-Path $stage 'Sortrr') -or
        $target -eq [IO.Path]::GetPathRoot($target).TrimEnd('\') -or
        -not (Test-Path -LiteralPath (Join-Path $target 'Sortrr.exe')) -or
        -not (Test-Path -LiteralPath (Join-Path $package 'Sortrr.exe')) -or
        -not (Test-Path -LiteralPath (Join-Path $package '_internal'))) {
        throw 'The installer paths are invalid.'
    }
    foreach ($path in @($target, $package, $stage)) {
        $item = Get-Item -LiteralPath $path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'The installer cannot replace linked application folders.'
        }
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    $id = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($target.ToLowerInvariant()))).Replace('-','')
    $mutex = New-Object Threading.Mutex($false, "Local\SortrrUpdate-$id")
    $locked = $mutex.WaitOne(0)
    if (-not $locked) { throw 'Another installer is already updating this copy of Sortrr.' }
    $process = Get-Process -Id $plan.pid -ErrorAction SilentlyContinue
    [IO.File]::WriteAllText((Join-Path $stage 'ready'), 'ready')
    if ($process -and -not $process.WaitForExit(120000)) {
        throw 'Sortrr is still running. Close it and check for updates again.'
    }
    $backup = Join-Path $stage 'previous'
    New-Item -ItemType Directory -Path $backup | Out-Null
    foreach ($name in $names) {
        $old = Join-Path $target $name
        if (Test-Path -LiteralPath $old) {
            Move-Item -LiteralPath $old -Destination (Join-Path $backup $name)
            $backed += $name
        }
    }
    foreach ($name in $names) {
        $new = Join-Path $package $name
        if (Test-Path -LiteralPath $new) {
            Move-Item -LiteralPath $new -Destination (Join-Path $target $name)
            $installed += $name
        }
    }
    "Installed $($plan.version). Previous app files remain in $backup" | Set-Content -LiteralPath $log
    $download = Join-Path $stage 'Sortrr-Windows-x64.zip'
    if (Test-Path -LiteralPath $download) {
        Remove-Item -LiteralPath $download -ErrorAction SilentlyContinue
    }
    $restarted = Start-Process -FilePath (Join-Path $target 'Sortrr.exe') -WorkingDirectory $target -PassThru
    if ($restarted.WaitForExit(3000)) {
        throw 'The updated app exited before it could finish starting.'
    }
}
catch {
    $failure = $_.Exception.Message
    if ($locked -and $backed.Count -gt 0) {
        try {
            foreach ($name in $installed) {
                Move-Item -LiteralPath (Join-Path $target $name) -Destination (Join-Path $package $name)
            }
            foreach ($name in $backed) {
                Move-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $target $name)
            }
            Start-Process -FilePath (Join-Path $target 'Sortrr.exe') -WorkingDirectory $target | Out-Null
        }
        catch { $failure += " Rollback issue: $($_.Exception.Message)" }
    }
    $failure | Set-Content -LiteralPath $log
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show("The Sortrr update could not finish. $failure" + [Environment]::NewLine + "Details are in $log", 'Sortrr update') | Out-Null
    exit 1
}
finally {
    if ($locked) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
}
