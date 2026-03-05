# Homelab AI Agent

## Overview
A Python-based AI agent for managing a Windows homelab via Discord. The agent provides control over VMware VMs, FL Studio file scanning and backup, and file management with a secure approval workflow.

## Project Architecture

### Core Modules
- **main.py** - Entry point, initializes all components and starts Discord bot
- **discord_bot.py** - Discord command interface using discord.py
- **orchestrator.py** - Workflow coordination and approval system
- **scanner.py** - FL Studio file scanner (.flp, .wav, .mp3, .fst)
- **vmware_controller.py** - VMware VM control via vmrun.exe
- **utils.py** - Shared utilities (logging, SQLite audit, file operations)

### Configuration
- **agent_config.yaml** - Main configuration file (Discord token, paths, settings)
- **requirements.txt** - Python dependencies

### Deployment
- **deploy_local.ps1** - PowerShell script for Windows deployment
- **README.md** - Comprehensive setup and usage documentation

## Key Features
1. Discord bot with command prefix (default: !)
2. Dry-run mode (enabled by default for safety)
3. Approval workflow for destructive actions
4. SQLite audit logging
5. Safe file operations (copy-verify-delete pattern)
6. VMware control via whitelisted VMs only

## Technology Stack
- Python 3.11+
- discord.py 2.3+
- PyYAML for configuration
- SQLite for audit logging

## Running the Project
This project is designed to run on Windows locally, not on Replit. The scaffold provides:
- All source code files
- Configuration templates
- Deployment scripts
- Documentation

To run on Windows:
1. Copy files to Windows machine
2. Run `deploy_local.ps1`
3. Configure `agent_config.yaml` with Discord token
4. Run `python main.py`

## Recent Changes
- 2024-12: Initial project scaffold created
  - Complete module structure
  - Discord bot with all commands
  - VMware controller
  - File scanner
  - Backup system with verification
  - Approval workflow
  - SQLite audit logging
  - Comprehensive documentation
