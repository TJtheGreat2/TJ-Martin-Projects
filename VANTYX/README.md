# Homelab AI Agent

A Python-based AI agent for managing your Windows homelab via Discord. Control VMware VMs, scan and backup FL Studio projects, and manage files with a secure approval workflow.

## Features

- **Discord Bot Interface** - Control your homelab from anywhere via Discord commands
- **FL Studio File Scanner** - Find and organize .flp, .wav, .mp3, and .fst files
- **VMware VM Control** - Start, stop, suspend, and snapshot VMs using vmrun.exe
- **Backup System** - Safely backup projects with hash verification
- **Approval Workflow** - Destructive actions require Discord approval
- **Audit Logging** - All actions logged to SQLite database
- **Dry-Run Mode** - Test safely without making real changes

## Requirements

- **Windows 10/11** or Windows Server 2016+
- **Python 3.11+** ([Download](https://www.python.org/downloads/))
- **VMware Workstation** (optional, for VM control)
- **Discord Account** with a bot application

---

## Quick Start

### 1. Download the Project

Download or clone this project to your Windows machine:

```powershell
# Example: to D:\AI\Agent
mkdir D:\AI\Agent
cd D:\AI\Agent
# Copy all project files here
```

### 2. Run the Deployment Script

Open PowerShell as Administrator and run:

```powershell
cd D:\AI\Agent
.\deploy_local.ps1
```

This will:
- Create the folder structure (D:\AI\Backups, D:\AI\Logs, etc.)
- Create a Python virtual environment
- Install all dependencies

### 3. Create a Discord Bot

Follow these steps to create your Discord bot:

#### Step 1: Create Application
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"**
3. Name it (e.g., "Homelab Agent")
4. Click **Create**

#### Step 2: Create Bot
1. Go to the **"Bot"** tab
2. Click **"Add Bot"**
3. Click **"Reset Token"** to generate a token
4. **Copy the token** - you'll need this!
5. Under **Privileged Gateway Intents**, enable:
   - **MESSAGE CONTENT INTENT** (required for commands)

#### Step 3: Invite Bot to Your Server
1. Go to the **"OAuth2"** tab
2. Select **"URL Generator"**
3. Under **Scopes**, check:
   - `bot`
   - `applications.commands`
4. Under **Bot Permissions**, check:
   - Send Messages
   - Read Message History
   - Embed Links
   - Add Reactions
5. Copy the generated URL and open it in your browser
6. Select your Discord server and authorize

### 4. Get Your Discord User ID

To use admin commands, you need your Discord User ID:

1. Open Discord
2. Go to **Settings** (gear icon)
3. Go to **Advanced**
4. Enable **"Developer Mode"**
5. Close settings
6. Right-click your username (anywhere in Discord)
7. Click **"Copy User ID"**

### 5. Configure the Agent

Edit `agent_config.yaml`:

```yaml
discord:
  # Paste your bot token here (keep the quotes!)
  bot_token: "YOUR_BOT_TOKEN_HERE"
  
  # Command prefix (default: !)
  command_prefix: "!"
  
  # Your Discord User ID (for admin privileges)
  admin_user_ids:
    - "YOUR_USER_ID_HERE"

agent:
  # Keep this TRUE until you've tested everything!
  dry_run: true
```

### 6. Start the Agent

```powershell
.\venv\Scripts\python.exe main.py
```

You should see:
```
Homelab AI Agent Starting
Configuration loaded from: agent_config.yaml
RUNNING IN DRY-RUN MODE
Starting Discord bot...
Bot logged in as YourBot#1234
```

---

## Discord Commands

### General Commands

| Command | Description |
|---------|-------------|
| `!help` | Show all available commands |
| `!status` | Get current system status |
| `!logs [count]` | View recent audit logs |

### File Scanner Commands

| Command | Description |
|---------|-------------|
| `!scan <path>` | Scan directory for FL Studio files |
| `!projects` | List found FL Studio projects |

**Example:**
```
!scan D:\Music\FL Studio
```

### Backup Commands

| Command | Description |
|---------|-------------|
| `!backup <file>` | Backup a specific file (immediate, respects dry-run) |
| `!backup_all [path]` | Backup all projects (requires approval) |
| `!request_backup <file>` | Request backup with approval workflow |

**Example:**
```
!backup D:\Music\MyProject.flp
```

### File Management Commands

| Command | Description |
|---------|-------------|
| `!move <source> <dest>` | Request file move (requires approval) |

**Example:**
```
!move D:\Music\OldProject.flp D:\Archive\OldProject.flp
```

### Approval Workflow Commands

| Command | Description |
|---------|-------------|
| `!pending` | List pending approval requests |
| `!approve <id>` | Approve a pending action (admin only) |
| `!deny <id>` | Deny a pending action (admin only) |
| `!execute` | Execute all approved actions (admin only) |

**Example workflow:**
```
User: !backup_all D:\Music
Bot: Approval required. Request #1 created.

Admin: !approve 1
Bot: Request #1 approved.

Admin: !execute
Bot: Executing approved actions... Done!
```

### VMware Commands

| Command | Description |
|---------|-------------|
| `!vm list` | List configured VMs and their status |
| `!vm start <name>` | Start a VM |
| `!vm stop <name>` | Stop a VM |
| `!vm snapshot <name> <snapshot_name>` | Create a snapshot |
| `!vm snapshots <name>` | List snapshots for a VM |

**Examples:**
```
!vm list
!vm start dev-server
!vm snapshot dev-server "Before update"
```

---

## Turning Off Dry-Run Mode

**IMPORTANT:** Dry-run mode is enabled by default for safety. In this mode, all commands are simulated - no files are moved, copied, or deleted, and VMs are not actually controlled.

### When to Disable Dry-Run

Only disable dry-run mode after:
1. You've tested all commands and they work as expected
2. You're confident in your configuration
3. You understand what each command will do

### How to Disable Dry-Run

Edit `agent_config.yaml`:

```yaml
agent:
  # Change from true to false
  dry_run: false
```

Then restart the agent:
```powershell
# Stop the agent (Ctrl+C)
# Start again
.\venv\Scripts\python.exe main.py
```

You'll see:
```
RUNNING IN LIVE MODE
File operations WILL be performed!
```

---

## Configuration Reference

### Discord Settings

```yaml
discord:
  bot_token: "YOUR_TOKEN"     # Discord bot token
  command_prefix: "!"          # Command prefix
  admin_user_ids:
    - "123456789012345678"     # Admin Discord User IDs
```

### Scanner Settings

```yaml
scanner:
  default_paths:
    - "D:/Music/FL Studio"     # Paths to scan by default
  extensions:
    - ".flp"                   # File types to find
    - ".wav"
    - ".mp3"
    - ".fst"
```

### Backup Settings

```yaml
backup:
  backup_path: "D:/AI/Backups" # Where to store backups
  preserve_structure: true      # Keep folder structure
  verify_backups: true          # Verify with SHA-256
```

### VMware Settings

```yaml
vmware:
  enabled: true
  vmrun_path: "C:/Program Files (x86)/VMware/VMware Workstation/vmrun.exe"
  vms:
    - name: "dev-server"
      vmx_path: "D:/VMs/DevServer/DevServer.vmx"
      description: "Development server"
```

---

## File Structure

```
homelab-agent/
├── main.py              # Entry point
├── discord_bot.py       # Discord commands
├── orchestrator.py      # Workflow coordination
├── scanner.py           # File scanner
├── vmware_controller.py # VM control
├── utils.py             # Shared utilities
├── agent_config.yaml    # Configuration
├── requirements.txt     # Python dependencies
├── deploy_local.ps1     # Windows setup script
├── audit.db             # SQLite audit database (created at runtime)
└── agent.log            # Log file (created at runtime)
```

---

## Security Features

### Safe by Design

1. **No Arbitrary Shell Execution** - The agent cannot run arbitrary commands
2. **Approval Workflow** - Destructive actions require admin approval
3. **Copy-Verify-Delete** - Files are copied and verified before removal
4. **Whitelisted VMs** - Only configured VMs can be controlled
5. **Audit Logging** - Every action is logged to SQLite
6. **Dry-Run Mode** - Test without making changes

### What Requires Approval

- Bulk backup operations
- File deletions
- VM snapshot reverts

---

## Troubleshooting

### Bot Not Responding

1. Check the bot is running (look for "Bot logged in as...")
2. Verify MESSAGE CONTENT INTENT is enabled in Discord Developer Portal
3. Check the bot has permissions in your Discord server

### "Configuration file not found"

Make sure `agent_config.yaml` exists in the same folder as `main.py`.

### "Invalid Discord bot token"

1. Go to Discord Developer Portal
2. Reset your bot token
3. Copy the new token to `agent_config.yaml`

### VMware Commands Not Working

1. Verify VMware Workstation is installed
2. Check the `vmrun_path` in config points to the correct location
3. Verify the VMX paths in your VM list are correct

### Files Not Being Backed Up

Check if you're in dry-run mode:
```
!status
```

If it says "DRY-RUN", set `dry_run: false` in config.

---

## Running as a Windows Service

To run the agent automatically on Windows startup:

1. Install NSSM (Non-Sucking Service Manager):
   ```powershell
   winget install nssm
   ```

2. Create the service:
   ```powershell
   nssm install HomelabAgent "D:\AI\Agent\venv\Scripts\python.exe" "D:\AI\Agent\main.py"
   nssm set HomelabAgent AppDirectory "D:\AI\Agent"
   ```

3. Start the service:
   ```powershell
   nssm start HomelabAgent
   ```

---

## License

This project is provided as-is for personal homelab use.

---

## Support

For issues or questions:
1. Check the `agent.log` file for errors
2. Review the audit log with `!logs 20`
3. Ensure your configuration is correct with `python main.py --validate`
