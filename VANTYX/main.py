"""
main.py - Homelab AI Agent Entry Point

This is the main entry point for the Homelab AI Agent.

The agent provides:
- Discord bot interface for remote control
- FL Studio file scanning and backup
- VMware VM management
- Approval workflow for destructive actions
- SQLite audit logging

Usage:
    python main.py
    python main.py --dry-run
    python main.py --config path/to/config.yaml

Environment:
    This agent is designed to run on Windows with:
    - Python 3.11+
    - VMware Workstation (optional)
    - Discord bot token configured in agent_config.yaml
"""

import asyncio
import argparse
import sys
from pathlib import Path

from utils import (
    load_config, 
    validate_config, 
    setup_logging, 
    AuditLogger
)
from scanner import FLStudioScanner
from vmware_controller import VMwareController
from orchestrator import Orchestrator, BackupManager
from discord_bot import run_bot

logger = setup_logging()


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Homelab AI Agent - Manage your homelab via Discord",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                    # Run with default config
    python main.py --dry-run          # Force dry-run mode
    python main.py --config my.yaml   # Use custom config file
    python main.py --validate         # Validate config only
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        default='agent_config.yaml',
        help='Path to configuration file (default: agent_config.yaml)'
    )
    
    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Force dry-run mode (no actual file operations)'
    )
    
    parser.add_argument(
        '--validate', '-v',
        action='store_true',
        help='Validate configuration and exit'
    )
    
    return parser.parse_args()


def initialize_components(config: dict, force_dry_run: bool = False):
    """
    Initialize all agent components.
    
    Args:
        config: Configuration dictionary
        force_dry_run: If True, override config to use dry-run mode
    
    Returns:
        Tuple of (audit_logger, scanner, vmware_controller, backup_manager, orchestrator)
    """
    dry_run = force_dry_run or config.get('agent', {}).get('dry_run', True)
    
    if dry_run:
        logger.warning("=" * 50)
        logger.warning("RUNNING IN DRY-RUN MODE")
        logger.warning("No actual file operations will be performed")
        logger.warning("=" * 50)
    else:
        logger.warning("=" * 50)
        logger.warning("RUNNING IN LIVE MODE")
        logger.warning("File operations WILL be performed!")
        logger.warning("=" * 50)
    
    db_path = config.get('agent', {}).get('database_path', 'audit.db')
    audit_logger = AuditLogger(db_path)
    logger.info(f"Audit logger initialized: {db_path}")
    
    scanner = FLStudioScanner(audit_logger)
    logger.info("File scanner initialized")
    
    vmware_controller = None
    vmware_config = config.get('vmware', {})
    
    if vmware_config.get('enabled', False):
        vmrun_path = vmware_config.get('vmrun_path', '')
        vms = vmware_config.get('vms', [])
        
        if vmrun_path and Path(vmrun_path).exists():
            vmware_controller = VMwareController(
                vmrun_path=vmrun_path,
                vms_config=vms,
                audit_logger=audit_logger,
                dry_run=dry_run
            )
            logger.info(f"VMware controller initialized with {len(vms)} VMs")
        else:
            logger.warning(f"VMware vmrun.exe not found at: {vmrun_path}")
            logger.warning("VMware features will be disabled")
    else:
        logger.info("VMware controller disabled in config")
    
    backup_root = config.get('backup', {}).get('backup_path', 'D:\\AI\\Backups')
    backup_manager = BackupManager(
        backup_root=backup_root,
        audit_logger=audit_logger,
        dry_run=dry_run
    )
    logger.info(f"Backup manager initialized: {backup_root}")
    
    orchestrator = Orchestrator(
        config=config,
        audit_logger=audit_logger,
        scanner=scanner,
        vmware_controller=vmware_controller,
        backup_manager=backup_manager
    )
    logger.info("Orchestrator initialized")
    
    return audit_logger, scanner, vmware_controller, backup_manager, orchestrator


async def main():
    """Main entry point."""
    args = parse_arguments()
    
    logger.info("=" * 60)
    logger.info("Homelab AI Agent Starting")
    logger.info("=" * 60)
    
    try:
        config = load_config(args.config)
        logger.info(f"Configuration loaded from: {args.config}")
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.error("Please create agent_config.yaml from the example file.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    errors = validate_config(config)
    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        
        if args.validate:
            sys.exit(1)
        
        if 'bot_token' in str(errors):
            logger.error("Cannot start without a valid Discord bot token.")
            sys.exit(1)
    else:
        logger.info("Configuration validation passed")
    
    if args.validate:
        logger.info("Configuration is valid.")
        sys.exit(0)
    
    try:
        (
            audit_logger,
            scanner,
            vmware_controller,
            backup_manager,
            orchestrator
        ) = initialize_components(config, args.dry_run)
    except Exception as e:
        logger.error(f"Failed to initialize components: {e}")
        sys.exit(1)
    
    logger.info("Starting Discord bot...")
    
    try:
        await run_bot(config, orchestrator, audit_logger)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        logger.info("Homelab AI Agent shutdown complete")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested. Goodbye!")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
