"""
discord_bot.py - Discord Bot Command Interface

This module provides Discord bot functionality for controlling the homelab agent.

Commands:
- !status - Get system status
- !scan <path> - Scan for FL Studio files
- !projects - List found FL Studio projects
- !backup <file> - Backup a specific file (immediate, dry-run safe)
- !backup_all <path> - Backup all projects (requires approval)
- !request_backup <file> - Request backup with approval workflow
- !move <source> <dest> - Request file move (requires approval)
- !approve <id> - Approve a pending action (admin only)
- !deny <id> - Deny a pending action (admin only)
- !execute - Execute all approved actions (admin only)
- !pending - List pending approvals
- !vm list - List configured VMs
- !vm start <name> - Start a VM
- !vm stop <name> - Stop a VM
- !vm snapshot <name> <snapshot_name> - Create VM snapshot
- !vm snapshots <name> - List VM snapshots
- !logs [count] - View recent audit logs
- !help - Show available commands

Security:
- Admin-only commands are restricted to configured admin user IDs
- All commands are logged to SQLite audit database
- Destructive actions (move, bulk backup) require approval workflow
- File moves use copy-verify-delete pattern for safety
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from typing import Optional
from datetime import datetime

from utils import AuditLogger, setup_logging, is_admin, format_size
from orchestrator import Orchestrator, ActionType

logger = setup_logging()


class HomelabBot(commands.Bot):
    """
    Discord bot for homelab management.
    
    This bot provides a command interface for:
    - File scanning and backup
    - VM control
    - Approval workflow management
    """
    
    def __init__(
        self,
        config: dict,
        orchestrator: Orchestrator,
        audit_logger: AuditLogger
    ):
        """
        Initialize the Discord bot.
        
        Args:
            config: Configuration dictionary
            orchestrator: Orchestrator instance
            audit_logger: AuditLogger instance
        """
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        prefix = config.get('discord', {}).get('command_prefix', '!')
        
        super().__init__(command_prefix=prefix, intents=intents)
        
        self.config = config
        self.orchestrator = orchestrator
        self.audit_logger = audit_logger
        self.admin_ids = [
            str(aid) for aid in config.get('discord', {}).get('admin_user_ids', [])
        ]
        
        self._setup_commands()
        
        logger.info(f"Discord bot initialized with prefix: {prefix}")
        logger.info(f"Admin user IDs: {self.admin_ids}")
    
    def _setup_commands(self) -> None:
        """Set up all bot commands."""
        
        @self.command(name='status')
        async def status_command(ctx):
            """Get current system status."""
            await self._cmd_status(ctx)
        
        @self.command(name='scan')
        async def scan_command(ctx, *, path: str = None):
            """Scan a directory for FL Studio files."""
            await self._cmd_scan(ctx, path)
        
        @self.command(name='projects')
        async def projects_command(ctx):
            """List found FL Studio projects."""
            await self._cmd_projects(ctx)
        
        @self.command(name='backup')
        async def backup_command(ctx, *, path: str):
            """Backup a specific file."""
            await self._cmd_backup(ctx, path)
        
        @self.command(name='backup_all')
        async def backup_all_command(ctx, *, path: str = None):
            """Backup all projects (requires approval)."""
            await self._cmd_backup_all(ctx, path)
        
        @self.command(name='approve')
        async def approve_command(ctx, request_id: int):
            """Approve a pending action (admin only)."""
            await self._cmd_approve(ctx, request_id)
        
        @self.command(name='deny')
        async def deny_command(ctx, request_id: int):
            """Deny a pending action (admin only)."""
            await self._cmd_deny(ctx, request_id)
        
        @self.command(name='pending')
        async def pending_command(ctx):
            """List pending approval requests."""
            await self._cmd_pending(ctx)
        
        @self.command(name='vm')
        async def vm_command(ctx, action: str = None, *, args: str = None):
            """VM control commands."""
            await self._cmd_vm(ctx, action, args)
        
        @self.command(name='logs')
        async def logs_command(ctx, count: int = 10):
            """View recent audit logs."""
            await self._cmd_logs(ctx, count)
        
        @self.command(name='execute')
        async def execute_command(ctx):
            """Execute all approved actions (admin only)."""
            await self._cmd_execute(ctx)
        
        @self.command(name='move')
        async def move_command(ctx, source: str, dest: str):
            """Request to move a file (requires approval)."""
            await self._cmd_move(ctx, source, dest)
        
        @self.command(name='request_backup')
        async def request_backup_command(ctx, *, path: str):
            """Request backup with approval (for sensitive files)."""
            await self._cmd_request_backup(ctx, path)
    
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        logger.info(f"Bot logged in as {self.user.name} ({self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="your homelab"
            )
        )
    
    async def on_command_error(self, ctx, error) -> None:
        """Handle command errors."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: {error.param.name}")
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            logger.error(f"Command error: {error}")
            await ctx.send(f"An error occurred: {str(error)[:200]}")
    
    def _is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        return str(user_id) in self.admin_ids
    
    def _log_command(self, ctx, command_name: str, details: str = None) -> None:
        """Log a command execution."""
        self.audit_logger.log_action(
            action_type=f'DISCORD_CMD_{command_name.upper()}',
            success=True,
            dry_run=False,
            user_id=str(ctx.author.id),
            user_name=str(ctx.author),
            details=details
        )
    
    async def _cmd_status(self, ctx) -> None:
        """Handle the status command."""
        self._log_command(ctx, 'status')
        
        status = self.orchestrator.get_status()
        
        embed = discord.Embed(
            title="Homelab Agent Status",
            color=discord.Color.green() if not status['dry_run'] else discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        mode = "LIVE" if not status['dry_run'] else "DRY-RUN (Safe Mode)"
        embed.add_field(name="Mode", value=mode, inline=True)
        embed.add_field(
            name="Pending Approvals", 
            value=str(status['pending_approvals']), 
            inline=True
        )
        
        if status['vmware']['enabled']:
            vm_count = len(status['vmware']['configured_vms'])
            embed.add_field(name="Configured VMs", value=str(vm_count), inline=True)
        else:
            embed.add_field(name="VMware", value="Not configured", inline=True)
        
        if status['scanner']['last_scan']:
            embed.add_field(
                name="Last Scan", 
                value=f"```{status['scanner']['last_scan'][:500]}```", 
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    async def _cmd_scan(self, ctx, path: str = None) -> None:
        """Handle the scan command."""
        if not path:
            default_paths = self.config.get('scanner', {}).get('default_paths', [])
            if default_paths:
                path = default_paths[0]
            else:
                await ctx.send("Please provide a path to scan: `!scan <path>`")
                return
        
        self._log_command(ctx, 'scan', f"Scanning: {path}")
        
        await ctx.send(f"Scanning `{path}` for FL Studio files...")
        
        result = await self.orchestrator.quick_scan(
            path,
            str(ctx.author.id),
            str(ctx.author)
        )
        
        embed = discord.Embed(
            title="Scan Results",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Path", value=path, inline=False)
        embed.add_field(name="Total Files", value=str(result['total_files']), inline=True)
        embed.add_field(name="Total Size", value=result['total_size_formatted'], inline=True)
        
        if result.get('file_counts'):
            counts_str = "\n".join([
                f"{ext}: {count}" for ext, count in result['file_counts'].items()
            ])
            embed.add_field(name="By Type", value=f"```{counts_str}```", inline=False)
        
        if result.get('errors'):
            error_str = "\n".join(result['errors'][:5])
            embed.add_field(name="Errors", value=f"```{error_str[:500]}```", inline=False)
        
        await ctx.send(embed=embed)
    
    async def _cmd_projects(self, ctx) -> None:
        """Handle the projects command."""
        self._log_command(ctx, 'projects')
        
        projects = self.orchestrator.scanner.find_flp_projects()
        
        if not projects:
            await ctx.send("No FL Studio projects found. Run `!scan <path>` first.")
            return
        
        embed = discord.Embed(
            title=f"FL Studio Projects ({len(projects)} found)",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        projects_sorted = sorted(projects, key=lambda x: x.modified, reverse=True)[:20]
        
        for project in projects_sorted:
            embed.add_field(
                name=project.name,
                value=f"Size: {format_size(project.size)}\nFolder: {project.parent_folder}\nModified: {project.modified.strftime('%Y-%m-%d')}",
                inline=True
            )
        
        if len(projects) > 20:
            embed.set_footer(text=f"Showing 20 of {len(projects)} projects")
        
        await ctx.send(embed=embed)
    
    async def _cmd_backup(self, ctx, path: str) -> None:
        """Handle the backup command."""
        self._log_command(ctx, 'backup', f"Backup: {path}")
        
        from pathlib import Path
        file_path = Path(path)
        
        if not file_path.exists():
            await ctx.send(f"File not found: `{path}`")
            return
        
        await ctx.send(f"Backing up `{file_path.name}`...")
        
        result = await self.orchestrator.backup_manager.backup_file(
            file_path,
            str(ctx.author.id),
            str(ctx.author)
        )
        
        if result['success']:
            if result['dry_run']:
                await ctx.send(f"[DRY-RUN] Would backup `{file_path.name}` to `{result['destination']}`")
            else:
                await ctx.send(f"Successfully backed up `{file_path.name}` (verified: {result.get('verified', False)})")
        else:
            await ctx.send(f"Backup failed: {result.get('error', 'Unknown error')}")
    
    async def _cmd_backup_all(self, ctx, path: str = None) -> None:
        """Handle the backup_all command."""
        if not path:
            default_paths = self.config.get('scanner', {}).get('default_paths', [])
            if default_paths:
                path = default_paths[0]
            else:
                await ctx.send("Please provide a path: `!backup_all <path>`")
                return
        
        self._log_command(ctx, 'backup_all', f"Backup all from: {path}")
        
        result = await self.orchestrator.backup_all_projects(
            path,
            str(ctx.author.id),
            str(ctx.author),
            require_approval=True
        )
        
        if result.get('approval_required'):
            embed = discord.Embed(
                title="Approval Required",
                description=f"Request #{result['request_id']} created",
                color=discord.Color.yellow()
            )
            embed.add_field(name="Projects", value=str(result['project_count']), inline=True)
            embed.add_field(name="Total Size", value=result['total_size'], inline=True)
            embed.add_field(
                name="Next Steps", 
                value=f"An admin must approve: `!approve {result['request_id']}`",
                inline=False
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(result.get('message', str(result)))
    
    async def _cmd_approve(self, ctx, request_id: int) -> None:
        """Handle the approve command (admin only)."""
        if not self._is_admin(ctx.author.id):
            await ctx.send("This command requires admin privileges.")
            return
        
        self._log_command(ctx, 'approve', f"Approved request #{request_id}")
        
        success = self.orchestrator.approve_action(request_id, str(ctx.author.id))
        
        if success:
            await ctx.send(f"Request #{request_id} approved. Run `!execute` to execute approved actions.")
        else:
            await ctx.send(f"Failed to approve request #{request_id}. It may not exist or already be approved.")
    
    async def _cmd_deny(self, ctx, request_id: int) -> None:
        """Handle the deny command (admin only)."""
        if not self._is_admin(ctx.author.id):
            await ctx.send("This command requires admin privileges.")
            return
        
        self._log_command(ctx, 'deny', f"Denied request #{request_id}")
        
        success = self.orchestrator.deny_action(request_id)
        
        if success:
            await ctx.send(f"Request #{request_id} denied and cancelled.")
        else:
            await ctx.send(f"Request #{request_id} not found.")
    
    async def _cmd_pending(self, ctx) -> None:
        """Handle the pending command."""
        self._log_command(ctx, 'pending')
        
        pending = self.orchestrator.get_pending_actions()
        
        if not pending:
            await ctx.send("No pending approval requests.")
            return
        
        embed = discord.Embed(
            title=f"Pending Approvals ({len(pending)})",
            color=discord.Color.yellow(),
            timestamp=datetime.now()
        )
        
        for action in pending[:10]:
            embed.add_field(
                name=f"#{action.id} - {action.action_type.value}",
                value=f"By: {action.requested_by_name}\nDetails: {action.details[:100]}\nCreated: {action.created_at.strftime('%Y-%m-%d %H:%M')}",
                inline=False
            )
        
        if len(pending) > 10:
            embed.set_footer(text=f"Showing 10 of {len(pending)} pending requests")
        
        await ctx.send(embed=embed)
    
    async def _cmd_vm(self, ctx, action: str = None, args: str = None) -> None:
        """Handle VM control commands."""
        if not self.orchestrator.vmware_controller:
            await ctx.send("VMware controller is not configured.")
            return
        
        if not action:
            action = 'list'
        
        action = action.lower()
        self._log_command(ctx, f'vm_{action}', args)
        
        vm_ctrl = self.orchestrator.vmware_controller
        
        if action == 'list':
            vms = vm_ctrl.list_configured_vms()
            if not vms:
                await ctx.send("No VMs configured.")
                return
            
            embed = discord.Embed(
                title="Configured Virtual Machines",
                color=discord.Color.blue()
            )
            
            running_result = await vm_ctrl.get_running_vms()
            running_paths = [p.lower() for p in running_result.get('running_vms', [])]
            
            for vm in vms:
                status = "Running" if vm['vmx_path'].lower() in running_paths else "Stopped"
                embed.add_field(
                    name=vm['name'],
                    value=f"Status: {status}\n{vm['description']}",
                    inline=True
                )
            
            await ctx.send(embed=embed)
        
        elif action == 'start':
            if not args:
                await ctx.send("Please specify a VM name: `!vm start <name>`")
                return
            
            vm_name = args.split()[0]
            await ctx.send(f"Starting VM `{vm_name}`...")
            
            result = await vm_ctrl.start_vm(
                vm_name, str(ctx.author.id), str(ctx.author)
            )
            
            if result['success']:
                if result['dry_run']:
                    await ctx.send(f"[DRY-RUN] Would start VM `{vm_name}`")
                else:
                    await ctx.send(f"VM `{vm_name}` started successfully.")
            else:
                await ctx.send(f"Failed to start VM: {result.get('error', 'Unknown error')}")
        
        elif action == 'stop':
            if not args:
                await ctx.send("Please specify a VM name: `!vm stop <name>`")
                return
            
            vm_name = args.split()[0]
            await ctx.send(f"Stopping VM `{vm_name}`...")
            
            result = await vm_ctrl.stop_vm(
                vm_name, str(ctx.author.id), str(ctx.author)
            )
            
            if result['success']:
                if result['dry_run']:
                    await ctx.send(f"[DRY-RUN] Would stop VM `{vm_name}`")
                else:
                    await ctx.send(f"VM `{vm_name}` stopped successfully.")
            else:
                await ctx.send(f"Failed to stop VM: {result.get('error', 'Unknown error')}")
        
        elif action == 'snapshot':
            if not args or len(args.split()) < 2:
                await ctx.send("Usage: `!vm snapshot <vm_name> <snapshot_name>`")
                return
            
            parts = args.split(maxsplit=1)
            vm_name = parts[0]
            snapshot_name = parts[1]
            
            await ctx.send(f"Creating snapshot `{snapshot_name}` for VM `{vm_name}`...")
            
            result = await vm_ctrl.create_snapshot(
                vm_name, snapshot_name, str(ctx.author.id), str(ctx.author)
            )
            
            if result['success']:
                if result['dry_run']:
                    await ctx.send(f"[DRY-RUN] Would create snapshot `{snapshot_name}` for VM `{vm_name}`")
                else:
                    await ctx.send(f"Snapshot `{snapshot_name}` created for VM `{vm_name}`.")
            else:
                await ctx.send(f"Failed to create snapshot: {result.get('error', 'Unknown error')}")
        
        elif action == 'snapshots':
            if not args:
                await ctx.send("Please specify a VM name: `!vm snapshots <name>`")
                return
            
            vm_name = args.split()[0]
            result = await vm_ctrl.list_snapshots(vm_name)
            
            if result['success']:
                snapshots = result.get('snapshots', [])
                if snapshots:
                    await ctx.send(f"Snapshots for `{vm_name}`:\n```\n" + "\n".join(snapshots) + "\n```")
                else:
                    await ctx.send(f"No snapshots found for `{vm_name}`.")
            else:
                await ctx.send(f"Failed to list snapshots: {result.get('error', 'Unknown error')}")
        
        else:
            await ctx.send(f"Unknown VM action: `{action}`. Available: list, start, stop, snapshot, snapshots")
    
    async def _cmd_logs(self, ctx, count: int = 10) -> None:
        """Handle the logs command."""
        self._log_command(ctx, 'logs', f"Count: {count}")
        
        count = min(count, 25)
        logs = self.audit_logger.get_recent_logs(count)
        
        if not logs:
            await ctx.send("No audit logs found.")
            return
        
        embed = discord.Embed(
            title=f"Recent Audit Logs ({len(logs)} entries)",
            color=discord.Color.greyple(),
            timestamp=datetime.now()
        )
        
        for log in logs[:10]:
            dry_run_marker = "[DRY]" if log['dry_run'] else ""
            status = "OK" if log['success'] else "FAIL"
            embed.add_field(
                name=f"{log['action_type']} {dry_run_marker} [{status}]",
                value=f"User: {log['user_name'] or 'System'}\nTime: {log['timestamp'][:16]}\n{(log['details'] or '')[:50]}",
                inline=False
            )
        
        if len(logs) > 10:
            embed.set_footer(text=f"Showing 10 of {len(logs)} entries")
        
        await ctx.send(embed=embed)
    
    async def _cmd_execute(self, ctx) -> None:
        """Handle the execute command (admin only)."""
        if not self._is_admin(ctx.author.id):
            await ctx.send("This command requires admin privileges.")
            return
        
        self._log_command(ctx, 'execute')
        
        await ctx.send("Executing approved actions...")
        
        results = await self.orchestrator.execute_approved_actions(
            str(ctx.author.id), str(ctx.author)
        )
        
        if not results:
            await ctx.send("No approved actions to execute.")
            return
        
        success_count = sum(1 for r in results if r.get('success'))
        fail_count = len(results) - success_count
        
        embed = discord.Embed(
            title="Execution Results",
            color=discord.Color.green() if fail_count == 0 else discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="Successful", value=str(success_count), inline=True)
        embed.add_field(name="Failed", value=str(fail_count), inline=True)
        
        for result in results[:5]:
            status = "Success" if result.get('success') else f"Failed: {result.get('error', 'Unknown')}"
            embed.add_field(
                name=f"#{result.get('id')} - {result.get('action_type', 'Unknown')}",
                value=status[:100],
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    async def _cmd_move(self, ctx, source: str, dest: str) -> None:
        """Handle the move command (requires approval)."""
        self._log_command(ctx, 'move', f"Move: {source} -> {dest}")
        
        from pathlib import Path
        source_path = Path(source)
        
        if not source_path.exists():
            await ctx.send(f"Source file not found: `{source}`")
            return
        
        action = self.orchestrator.request_approval(
            action_type=ActionType.FILE_MOVE,
            requested_by=str(ctx.author.id),
            requested_by_name=str(ctx.author),
            details=f"Move file from {source} to {dest}",
            source_path=source,
            dest_path=dest
        )
        
        embed = discord.Embed(
            title="Move Request Created",
            description=f"Request #{action.id} requires admin approval",
            color=discord.Color.yellow(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Source", value=f"`{source}`", inline=False)
        embed.add_field(name="Destination", value=f"`{dest}`", inline=False)
        embed.add_field(
            name="Next Steps",
            value=f"An admin must run: `!approve {action.id}`\nThen run: `!execute`",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    async def _cmd_request_backup(self, ctx, path: str) -> None:
        """Handle the request_backup command (requires approval)."""
        self._log_command(ctx, 'request_backup', f"Request backup: {path}")
        
        from pathlib import Path
        file_path = Path(path)
        
        if not file_path.exists():
            await ctx.send(f"File not found: `{path}`")
            return
        
        backup_dest = self.orchestrator.backup_manager._get_backup_folder() / file_path.name
        
        action = self.orchestrator.request_approval(
            action_type=ActionType.FILE_BACKUP,
            requested_by=str(ctx.author.id),
            requested_by_name=str(ctx.author),
            details=f"Backup file {file_path.name} ({format_size(file_path.stat().st_size)})",
            source_path=path,
            dest_path=str(backup_dest)
        )
        
        embed = discord.Embed(
            title="Backup Request Created",
            description=f"Request #{action.id} requires admin approval",
            color=discord.Color.yellow(),
            timestamp=datetime.now()
        )
        embed.add_field(name="File", value=f"`{file_path.name}`", inline=True)
        embed.add_field(name="Size", value=format_size(file_path.stat().st_size), inline=True)
        embed.add_field(
            name="Next Steps",
            value=f"An admin must run: `!approve {action.id}`\nThen run: `!execute`",
            inline=False
        )
        
        await ctx.send(embed=embed)


async def run_bot(
    config: dict,
    orchestrator: Orchestrator,
    audit_logger: AuditLogger
) -> None:
    """
    Run the Discord bot.
    
    Args:
        config: Configuration dictionary
        orchestrator: Orchestrator instance
        audit_logger: AuditLogger instance
    """
    bot_token = config.get('discord', {}).get('bot_token')
    
    if not bot_token:
        logger.error("Discord bot token not configured!")
        raise ValueError("Discord bot token is required in agent_config.yaml")
    
    bot = HomelabBot(config, orchestrator, audit_logger)
    
    try:
        await bot.start(bot_token)
    except discord.LoginFailure:
        logger.error("Invalid Discord bot token!")
        raise
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
