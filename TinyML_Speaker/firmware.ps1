param(
    [ValidateSet('setup', 'build', 'upload', 'boards')]
    [string]$Action = 'build',
    [string]$Port
)
$ErrorActionPreference = 'Stop'
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
        Invoke-Arduino compile --fqbn arduino:mbed_nano:nano33ble $sketch
        if ($Action -eq 'upload') {
            if (-not $Port) { throw 'Supply -Port COMn. Use firmware.ps1 boards to list ports.' }
            Invoke-Arduino upload --fqbn arduino:mbed_nano:nano33ble --port $Port $sketch
        }
    }
} finally {
    & subst $drive /D
}
