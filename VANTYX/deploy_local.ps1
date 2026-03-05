<#
.SYNOPSIS
    Homelab AI Agent - Windows Deployment Script

.DESCRIPTION
    This PowerShell script automates the setup of the Homelab AI Agent on Windows.
    
    It performs the following:
    1. Creates the D:\AI folder structure
    2. Creates a Python virtual environment
    3. Installs Python dependencies
    4. Creates a template configuration file
    5. Optionally starts the agent

.NOTES
    Requirements:
    - Windows 10/11 or Windows Server 2016+
    - Python 3.11+ installed and in PATH
    - PowerShell 5.1+ (usually pre-installed)
    
    Run this script from the project directory:
    .\deploy_local.ps1

.EXAMPLE
    # Basic deployment
    .\deploy_local.ps1
    
    # Skip starting the agent after setup
    .\deploy_local.ps1 -NoStart
    
    # Use a custom Python path
    .\deploy_local.ps1 -PythonPath "C:\Python311\python.exe"

#>

param(
    # Don't start the agent after setup
    [switch]$NoStart,
    
    # Custom Python executable path
    [string]$PythonPath = "python",
    
    # Custom base directory for AI files
    [string]$BaseDir = "D:\AI",
    
    # Skip creating directories
    [switch]$SkipDirs,
    
    # Force recreation of virtual environment
    [switch]$ForceVenv
)

# ============================================================================
# CONFIGURATION
# ============================================================================

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Success { param($Message) Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Info { param($Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Warn { param($Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Err { param($Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

# ============================================================================
# BANNER
# ============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  HOMELAB AI AGENT - WINDOWS DEPLOYMENT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# STEP 1: CHECK PYTHON
# ============================================================================

Write-Info "Checking Python installation..."

try {
    $pythonVersion = & $PythonPath --version 2>&1
    Write-Success "Found: $pythonVersion"
    
    # Check version is 3.11+
    $versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
    if ($versionMatch) {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
            Write-Err "Python 3.11+ is required. Found: $pythonVersion"
            Write-Info "Download Python 3.11+ from https://www.python.org/downloads/"
            exit 1
        }
    }
} catch {
    Write-Err "Python not found. Please install Python 3.11+ and add it to PATH."
    Write-Info "Download from: https://www.python.org/downloads/"
    exit 1
}

# ============================================================================
# STEP 2: CREATE DIRECTORY STRUCTURE
# ============================================================================

if (-not $SkipDirs) {
    Write-Info "Creating directory structure..."
    
    $directories = @(
        "$BaseDir",
        "$BaseDir\Agent",
        "$BaseDir\Backups",
        "$BaseDir\Logs",
        "$BaseDir\Config"
    )
    
    foreach ($dir in $directories) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Success "Created: $dir"
        } else {
            Write-Info "Exists: $dir"
        }
    }
}

# ============================================================================
# STEP 3: CREATE VIRTUAL ENVIRONMENT
# ============================================================================

$venvPath = ".\venv"
$venvActivate = "$venvPath\Scripts\Activate.ps1"

if ((Test-Path $venvPath) -and -not $ForceVenv) {
    Write-Info "Virtual environment already exists."
} else {
    if ($ForceVenv -and (Test-Path $venvPath)) {
        Write-Warn "Removing existing virtual environment..."
        Remove-Item -Recurse -Force $venvPath
    }
    
    Write-Info "Creating Python virtual environment..."
    & $PythonPath -m venv $venvPath
    
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment."
        exit 1
    }
    
    Write-Success "Virtual environment created: $venvPath"
}

# ============================================================================
# STEP 4: ACTIVATE VENV AND INSTALL DEPENDENCIES
# ============================================================================

Write-Info "Activating virtual environment..."

# Activate the virtual environment
& $venvActivate

# Upgrade pip
Write-Info "Upgrading pip..."
& "$venvPath\Scripts\python.exe" -m pip install --upgrade pip --quiet

# Install requirements
Write-Info "Installing Python dependencies..."
& "$venvPath\Scripts\pip.exe" install -r requirements.txt --quiet

if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to install dependencies."
    exit 1
}

Write-Success "Dependencies installed successfully."

# ============================================================================
# STEP 5: CREATE CONFIGURATION FILE
# ============================================================================

$configFile = "agent_config.yaml"
$exampleConfig = "agent_config.yaml"  # The example is the main file now

if (-not (Test-Path $configFile)) {
    Write-Warn "Configuration file not found."
    Write-Info "Please edit $configFile with your Discord bot token and settings."
} else {
    Write-Info "Configuration file exists: $configFile"
}

# ============================================================================
# STEP 6: VERIFY SETUP
# ============================================================================

Write-Host ""
Write-Info "Verifying installation..."

# Check if main.py exists
if (Test-Path "main.py") {
    Write-Success "main.py found"
} else {
    Write-Err "main.py not found. Are you in the project directory?"
    exit 1
}

# Run validation
Write-Info "Validating configuration..."
$validateResult = & "$venvPath\Scripts\python.exe" main.py --validate 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Success "Configuration is valid."
} else {
    Write-Warn "Configuration needs attention. See above for details."
    Write-Info "Edit agent_config.yaml and add your Discord bot token."
}

# ============================================================================
# SUMMARY
# ============================================================================

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Directory structure:"
Write-Host "  $BaseDir\Agent   - Agent files and database" -ForegroundColor Gray
Write-Host "  $BaseDir\Backups - FL Studio project backups" -ForegroundColor Gray
Write-Host "  $BaseDir\Logs    - Log files" -ForegroundColor Gray
Write-Host "  $BaseDir\Config  - Configuration files" -ForegroundColor Gray
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Edit agent_config.yaml with your Discord bot token" -ForegroundColor White
Write-Host "  2. Add your Discord User ID to admin_user_ids" -ForegroundColor White
Write-Host "  3. Configure VMware paths if using VM control" -ForegroundColor White
Write-Host "  4. Run: .\venv\Scripts\python.exe main.py" -ForegroundColor White
Write-Host ""

# ============================================================================
# OPTIONAL: START THE AGENT
# ============================================================================

if (-not $NoStart) {
    Write-Host "Would you like to start the agent now? (y/n)" -ForegroundColor Yellow
    $response = Read-Host
    
    if ($response -eq 'y' -or $response -eq 'Y') {
        Write-Info "Starting Homelab AI Agent..."
        Write-Info "Press Ctrl+C to stop."
        Write-Host ""
        
        & "$venvPath\Scripts\python.exe" main.py
    } else {
        Write-Info "To start the agent later, run:"
        Write-Host "  .\venv\Scripts\python.exe main.py" -ForegroundColor White
    }
}

Write-Host ""
