param(
    [ValidateSet('setup', 'build', 'upload', 'boards')]
    [string]$Action = 'build',
    [string]$Port,
    [string]$Name
)
$ErrorActionPreference = 'Stop'
if ($Name -and $Name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,19}$') {
    throw 'Use a badge name of 1-20 letters, digits, underscores, or hyphens, starting with a letter or digit.'
}
$nameHeader = Join-Path $PSScriptRoot 'firmware/SpeakerBadge/badge_name.h'
$cli = Join-Path $PSScriptRoot '.tools/arduino-cli.exe'
if (-not (Test-Path -LiteralPath $cli)) {
    $command = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if ($command) { $cli = $command.Source }
    else { throw 'Install Arduino CLI on PATH, or place arduino-cli.exe in .tools.' }
}
$config = Join-Path $PSScriptRoot '.tools/arduino-cli.yaml'
New-Item -ItemType Directory -Force (Split-Path $config) | Out-Null
# The board's GCC version cannot resolve its own headers under long Windows paths.
$drive = @('Z:', 'Y:', 'X:', 'W:', 'V:', 'U:', 'T:') | Where-Object {
    -not (Test-Path "$_\")
} | Select-Object -First 1
if (-not $drive) { throw 'No free drive letter T: through Z: for the temporary build path.' }
& subst $drive (Join-Path $PSScriptRoot '.tools')
if ($LASTEXITCODE -ne 0) { throw 'Could not create temporary toolchain drive.' }
try {
    "directories:`n  data: '$drive/data'`n  downloads: '$drive/downloads'`n  user: '$drive/user'" | Set-Content -LiteralPath $config
    function Invoke-Arduino {
        & $cli --config-file $config @args
        if ($LASTEXITCODE -ne 0) { throw "Arduino CLI failed: $args" }
    }
    if ($Action -eq 'setup') {
        Invoke-Arduino core update-index
        Invoke-Arduino core install arduino:mbed_nano
        foreach ($library in @('ArduinoBLE', 'Arduino_BMI270_BMM150', 'Arduino_HS300x', 'Arduino_LPS22HB', 'Arduino_APDS9960')) {
            Invoke-Arduino lib install $library
        }
    } elseif ($Action -eq 'boards') {
        Invoke-Arduino board list
    } else {
        $sketch = Join-Path $PSScriptRoot 'firmware/SpeakerBadge'
        if ($Name) {
            "#define BADGE_NAME `"$Name`"" | Set-Content -LiteralPath $nameHeader
            Write-Host "Building firmware that advertises as $Name"
        } elseif ($Action -eq 'upload') {
            Write-Warning 'No -Name given. The badge advertises the shared default name and the PC numbers it by scan order.'
        }
        Invoke-Arduino compile --fqbn arduino:mbed_nano:nano33ble $sketch
        if ($Action -eq 'upload') {
            if (-not $Port) { throw 'Supply -Port COMn. Use firmware.ps1 boards to list ports.' }
            Invoke-Arduino upload --fqbn arduino:mbed_nano:nano33ble --port $Port $sketch
        }
    }
} finally {
    Remove-Item -LiteralPath $nameHeader -ErrorAction SilentlyContinue
    & subst $drive /D
}
