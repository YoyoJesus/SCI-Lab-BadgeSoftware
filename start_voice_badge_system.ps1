# Voice Badge Data Collection System Launcher
# This script starts both data collection and live graph viewer as separate processes

param(
    [switch]$Help,
    [switch]$DataOnly,
    [switch]$GraphOnly,
    [int]$DelaySeconds = 3
)

# Function to display help
function Show-Help {
    Write-Host "Voice Badge System Launcher" -ForegroundColor Cyan
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\start_voice_badge_system.ps1                 # Start both data collection and graph viewer"
    Write-Host "  .\start_voice_badge_system.ps1 -DataOnly       # Start only data collection"
    Write-Host "  .\start_voice_badge_system.ps1 -GraphOnly      # Start only graph viewer"
    Write-Host "  .\start_voice_badge_system.ps1 -DelaySeconds 5 # Custom delay between starting processes"
    Write-Host "  .\start_voice_badge_system.ps1 -Help           # Show this help message"
    Write-Host ""
    Write-Host "Parameters:" -ForegroundColor Yellow
    Write-Host "  -DataOnly      : Only start the data collection process"
    Write-Host "  -GraphOnly     : Only start the graph viewer process"
    Write-Host "  -DelaySeconds  : Delay in seconds between starting processes (default: 3)"
    Write-Host "  -Help          : Show this help message"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\start_voice_badge_system.ps1                 # Normal startup"
    Write-Host "  .\start_voice_badge_system.ps1 -DelaySeconds 5 # Wait 5 seconds between processes"
    exit
}

# Show help if requested
if ($Help) {
    Show-Help
}

# Get the script directory (root directory)
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

Write-Host "[LAUNCHER] Voice Badge Data Collection System" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "[INFO] Working Directory: $ScriptRoot" -ForegroundColor Gray
Write-Host ""

# Function to check if Python is available
function Test-PythonAvailable {
    try {
        $pythonVersion = python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Python found: $pythonVersion" -ForegroundColor Green
            return $true
        }
    }
    catch {
        Write-Host "[ERROR] Python not found in PATH" -ForegroundColor Red
        Write-Host "[TIP] Please install Python or add it to your PATH" -ForegroundColor Yellow
        return $false
    }
    return $false
}

# Function to check if required files exist
function Test-RequiredFiles {
    $requiredFiles = @(
        "Data Collection & Visualization/data_collection.py",
        "Data Collection & Visualization/live_graph_viewer.py"
    )
    $allFilesExist = $true
    
    foreach ($file in $requiredFiles) {
        if (Test-Path $file) {
            Write-Host "[OK] Found: $file" -ForegroundColor Green
        } else {
            Write-Host "[ERROR] Missing: $file" -ForegroundColor Red
            $allFilesExist = $false
        }
    }
    
    return $allFilesExist
}

# Function to start a Python process
function Start-PythonProcess {
    param(
        [string]$ScriptName,
        [string]$ProcessName,
        [string]$Icon
    )
    
    try {
        Write-Host "[$Icon] Starting $ProcessName..." -ForegroundColor Yellow
        
        # Get the full path to the script
        $fullScriptPath = Join-Path -Path $ScriptRoot -ChildPath "Data Collection & Visualization" | Join-Path -ChildPath (Split-Path -Leaf $ScriptName)
        
        # Start the process with explicit working directory and better error handling
        $processInfo = New-Object System.Diagnostics.ProcessStartInfo
        $processInfo.FileName = "python"
        $processInfo.Arguments = "`"$fullScriptPath`""
        $processInfo.WorkingDirectory = $ScriptRoot
        $processInfo.UseShellExecute = $true
        $processInfo.CreateNoWindow = $false
        $processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
        
        $process = [System.Diagnostics.Process]::Start($processInfo)
        
        if ($process) {
            # Give the process a moment to start and check if it's still running
            Start-Sleep -Milliseconds 500
            if (!$process.HasExited) {
                Write-Host "[OK] $ProcessName started successfully (PID: $($process.Id))" -ForegroundColor Green
                return $process
            } else {
                Write-Host "[ERROR] $ProcessName exited immediately (Exit Code: $($process.ExitCode))" -ForegroundColor Red
                return $null
            }
        } else {
            Write-Host "[ERROR] Failed to start $ProcessName" -ForegroundColor Red
            return $null
        }
    }
    catch {
        Write-Host "[ERROR] Error starting $ProcessName : $_" -ForegroundColor Red
        return $null
    }
}

# Function to monitor processes
function Monitor-Processes {
    param([array]$Processes)
    
    Write-Host ""
    Write-Host "[MONITOR] Process Monitor" -ForegroundColor Cyan
    Write-Host "=========================" -ForegroundColor Cyan
    Write-Host "[TIP] Press Ctrl+C to stop monitoring and optionally terminate processes" -ForegroundColor Yellow
    Write-Host ""
    
    try {
        $monitorCount = 0
        while ($true) {
            $runningProcesses = @()
            $exitedProcesses = @()
            
            foreach ($proc in $Processes) {
                if ($proc) {
                    if (!$proc.HasExited) {
                        $runningProcesses += $proc
                    } else {
                        $exitedProcesses += @{
                            Process = $proc
                            ExitCode = $proc.ExitCode
                            ExitTime = $proc.ExitTime
                        }
                    }
                }
            }
            
            if ($runningProcesses.Count -eq 0) {
                Write-Host "[INFO] All processes have ended." -ForegroundColor Yellow
                
                # Show exit information for debugging
                if ($exitedProcesses.Count -gt 0) {
                    Write-Host ""
                    Write-Host "[DEBUG] Process Exit Information:" -ForegroundColor Cyan
                    foreach ($exitInfo in $exitedProcesses) {
                        $exitCode = $exitInfo.ExitCode
                        $exitTime = $exitInfo.ExitTime
                        Write-Host "[DEBUG] PID $($exitInfo.Process.Id) exited with code $exitCode at $exitTime" -ForegroundColor Gray
                        
                        if ($exitCode -eq 0) {
                            Write-Host "[INFO] Exit code 0 = Normal completion" -ForegroundColor Green
                        } else {
                            Write-Host "[WARNING] Exit code $exitCode = Process ended with error or early termination" -ForegroundColor Yellow
                        }
                    }
                }
                break
            }
            
            $monitorCount++
            Write-Host "[STATUS] Running processes: $($runningProcesses.Count) (Check #$monitorCount)" -ForegroundColor Green
            Start-Sleep -Seconds 5
        }
    }
    catch {
        Write-Host ""
        Write-Host "[INTERRUPT] Monitoring interrupted by user" -ForegroundColor Yellow
        
        # Ask user if they want to terminate running processes
        $runningProcesses = @()
        foreach ($proc in $Processes) {
            if ($proc -and !$proc.HasExited) {
                $runningProcesses += $proc
            }
        }
        
        if ($runningProcesses.Count -gt 0) {
            Write-Host ""
            $response = Read-Host "[QUESTION] Do you want to terminate the running processes? (y/N)"
            if ($response -eq 'y' -or $response -eq 'Y') {
                foreach ($proc in $runningProcesses) {
                    try {
                        Write-Host "[STOP] Terminating process (PID: $($proc.Id))..." -ForegroundColor Yellow
                        $proc.Kill()
                        Write-Host "[OK] Process terminated" -ForegroundColor Green
                    }
                    catch {
                        Write-Host "[ERROR] Failed to terminate process: $_" -ForegroundColor Red
                    }
                }
            } else {
                Write-Host "[INFO] Processes left running in background" -ForegroundColor Gray
            }
        }
    }
}

# Main execution
try {
    # Check prerequisites
    if (!(Test-PythonAvailable)) {
        exit 1
    }
    
    if (!(Test-RequiredFiles)) {
        Write-Host ""
        Write-Host "[ERROR] Required files are missing. Please ensure you're in the correct directory." -ForegroundColor Red
        exit 1
    }
    
    Write-Host ""
    Write-Host "[START] Starting processes..." -ForegroundColor Cyan
    Write-Host ""
    
    $processes = @()
    
    # Start data collection if not GraphOnly
    if (!$GraphOnly) {
        $dataProcess = Start-PythonProcess -ScriptName "data_collection.py" -ProcessName "Data Collection" -Icon "DATA"
        if ($dataProcess) {
            $processes += $dataProcess
            
            if (!$DataOnly) {
                Write-Host "[WAIT] Waiting $DelaySeconds seconds before starting graph viewer..." -ForegroundColor Gray
                Start-Sleep -Seconds $DelaySeconds
            }
        } else {
            Write-Host "[ERROR] Failed to start data collection. Aborting." -ForegroundColor Red
            exit 1
        }
    }
    
    # Start graph viewer if not DataOnly
    if (!$DataOnly) {
        $graphProcess = Start-PythonProcess -ScriptName "live_graph_viewer.py" -ProcessName "Live Graph Viewer" -Icon "GRAPH"
        if ($graphProcess) {
            $processes += $graphProcess
        } else {
            Write-Host "[WARNING] Graph viewer failed to start, but data collection may still be running" -ForegroundColor Yellow
        }
    }
    
    if ($processes.Count -eq 0) {
        Write-Host "[ERROR] No processes were started successfully" -ForegroundColor Red
        exit 1
    }
    
    Write-Host ""
    Write-Host "[SUCCESS] Voice Badge System is now running!" -ForegroundColor Green
    Write-Host "=============================================" -ForegroundColor Green
    
    if (!$GraphOnly) {
        Write-Host "[DATA] Data Collection: Collecting data from voice badges" -ForegroundColor Cyan
        Write-Host "[TIP] If data collection exits quickly, ensure badges are nearby and powered on" -ForegroundColor Yellow
    }
    if (!$DataOnly) {
        Write-Host "[GRAPH] Live Graph Viewer: Real-time visualization with badge controls" -ForegroundColor Cyan
        Write-Host "[TIP] Graph viewer needs CSV data files to display - run data collection first" -ForegroundColor Yellow
    }
    
    # Monitor processes
    Monitor-Processes -Processes $processes
    
} catch {
    Write-Host ""
    Write-Host "[ERROR] An unexpected error occurred: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[COMPLETE] Voice Badge System Launcher completed" -ForegroundColor Green
