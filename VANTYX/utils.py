"""
utils.py - Core utility functions for the Homelab AI Agent

This module provides:
- SQLite audit logging for all operations
- File logging setup
- Safe file operations (copy with verification)
- Configuration loading from YAML
- Helper functions used across all modules

Security Note: All file operations use copy-verify-then-delete pattern.
No arbitrary shell execution is allowed.
"""

import sqlite3
import logging
import hashlib
import shutil
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(log_file: str = "agent.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configure file and console logging for the agent.
    
    Args:
        log_file: Path to the log file
        level: Logging level (default: INFO)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("homelab_agent")
    logger.setLevel(level)
    
    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger


# ============================================================================
# SQLITE AUDIT LOGGING
# ============================================================================

class AuditLogger:
    """
    SQLite-based audit logger for tracking all agent operations.
    
    Every action (file moves, VM operations, backups) is logged with:
    - Timestamp
    - Action type
    - User who initiated (Discord user ID)
    - Details of the operation
    - Success/failure status
    - Dry-run indicator
    """
    
    def __init__(self, db_path: str = "audit.db"):
        """Initialize the audit database."""
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self) -> None:
        """Create the audit tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    user_id TEXT,
                    user_name TEXT,
                    details TEXT,
                    source_path TEXT,
                    dest_path TEXT,
                    success INTEGER NOT NULL,
                    dry_run INTEGER NOT NULL,
                    error_message TEXT
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    details TEXT,
                    source_path TEXT,
                    dest_path TEXT,
                    approved INTEGER DEFAULT 0,
                    approved_by TEXT,
                    approved_at TEXT,
                    executed INTEGER DEFAULT 0
                )
            """)
            
            conn.commit()
    
    def log_action(
        self,
        action_type: str,
        success: bool,
        dry_run: bool,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        details: Optional[str] = None,
        source_path: Optional[str] = None,
        dest_path: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> int:
        """
        Log an action to the audit database.
        
        Args:
            action_type: Type of action (FILE_SCAN, VM_START, BACKUP, etc.)
            success: Whether the operation succeeded
            dry_run: Whether this was a dry-run (simulated) operation
            user_id: Discord user ID who initiated the action
            user_name: Discord username
            details: Additional details about the operation
            source_path: Source file/VM path
            dest_path: Destination path (for moves/copies)
            error_message: Error message if operation failed
        
        Returns:
            The ID of the inserted log entry
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_log 
                (timestamp, action_type, user_id, user_name, details, 
                 source_path, dest_path, success, dry_run, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                action_type,
                user_id,
                user_name,
                details,
                source_path,
                dest_path,
                1 if success else 0,
                1 if dry_run else 0,
                error_message
            ))
            conn.commit()
            return cursor.lastrowid or 0
    
    def create_approval_request(
        self,
        action_type: str,
        requested_by: str,
        details: str,
        source_path: Optional[str] = None,
        dest_path: Optional[str] = None
    ) -> int:
        """
        Create a pending approval request for a destructive action.
        
        Args:
            action_type: Type of action requiring approval
            requested_by: Discord user ID of requester
            details: Description of the requested action
            source_path: Source file/VM path
            dest_path: Destination path
        
        Returns:
            The approval request ID
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pending_approvals
                (created_at, action_type, requested_by, details, source_path, dest_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                action_type,
                requested_by,
                details,
                source_path,
                dest_path
            ))
            conn.commit()
            return cursor.lastrowid or 0
    
    def approve_request(self, request_id: int, approved_by: str) -> bool:
        """
        Mark an approval request as approved.
        
        Args:
            request_id: The approval request ID
            approved_by: Discord user ID of the approver
        
        Returns:
            True if approval was successful
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_approvals
                SET approved = 1, approved_by = ?, approved_at = ?
                WHERE id = ? AND approved = 0
            """, (approved_by, datetime.now().isoformat(), request_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """Get all pending (unapproved) requests."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pending_approvals
                WHERE approved = 0
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_approved_unexecuted(self) -> List[Dict[str, Any]]:
        """Get approved requests that haven't been executed yet."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pending_approvals
                WHERE approved = 1 AND executed = 0
                ORDER BY approved_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def mark_executed(self, request_id: int) -> None:
        """Mark an approved request as executed."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE pending_approvals
                SET executed = 1
                WHERE id = ?
            """, (request_id,))
            conn.commit()
    
    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the most recent audit log entries."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM audit_log
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# CONFIGURATION LOADING
# ============================================================================

def load_config(config_path: str = "agent_config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to the configuration file
    
    Returns:
        Configuration dictionary
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please copy agent_config.example.yaml to {config_path} and configure it."
        )
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def validate_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate the configuration and return any errors.
    
    Args:
        config: Configuration dictionary
    
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if not config.get('discord', {}).get('bot_token'):
        errors.append("Discord bot token is required")
    
    if not config.get('discord', {}).get('admin_user_ids'):
        errors.append("At least one admin user ID is required")
    
    vmware_config = config.get('vmware', {})
    if vmware_config.get('enabled', False):
        vmrun_path = vmware_config.get('vmrun_path')
        if vmrun_path and not Path(vmrun_path).exists():
            errors.append(f"vmrun.exe not found at: {vmrun_path}")
    
    return errors


# ============================================================================
# SAFE FILE OPERATIONS
# ============================================================================

def calculate_file_hash(file_path: Path, algorithm: str = 'sha256') -> str:
    """
    Calculate the hash of a file for verification.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use
    
    Returns:
        Hexadecimal hash string
    """
    hash_func = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def safe_copy_file(
    source: Path,
    destination: Path,
    verify: bool = True,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Safely copy a file with optional verification.
    
    This function:
    1. Checks source exists
    2. Creates destination directory if needed
    3. Copies the file
    4. Verifies the copy matches the original (if verify=True)
    
    Args:
        source: Source file path
        destination: Destination file path
        verify: Whether to verify the copy with hash comparison
        dry_run: If True, simulate the operation without copying
    
    Returns:
        Dictionary with operation results
    """
    result = {
        'success': False,
        'source': str(source),
        'destination': str(destination),
        'dry_run': dry_run,
        'verified': False,
        'error': None
    }
    
    if not source.exists():
        result['error'] = f"Source file not found: {source}"
        return result
    
    if not source.is_file():
        result['error'] = f"Source is not a file: {source}"
        return result
    
    if dry_run:
        result['success'] = True
        result['message'] = f"[DRY-RUN] Would copy {source} to {destination}"
        return result
    
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(source, destination)
        
        if verify:
            source_hash = calculate_file_hash(source)
            dest_hash = calculate_file_hash(destination)
            
            if source_hash == dest_hash:
                result['verified'] = True
                result['success'] = True
            else:
                destination.unlink()
                result['error'] = "File verification failed - hashes don't match"
        else:
            result['success'] = True
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


def safe_move_file(
    source: Path,
    destination: Path,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Safely move a file using copy-verify-delete pattern.
    
    Security: This never deletes the source until the copy is verified.
    
    Args:
        source: Source file path
        destination: Destination file path
        dry_run: If True, simulate the operation
    
    Returns:
        Dictionary with operation results
    """
    copy_result = safe_copy_file(source, destination, verify=True, dry_run=dry_run)
    
    if not copy_result['success']:
        return copy_result
    
    if dry_run:
        copy_result['message'] = f"[DRY-RUN] Would move {source} to {destination}"
        return copy_result
    
    if copy_result['verified']:
        try:
            source.unlink()
            copy_result['source_deleted'] = True
        except Exception as e:
            copy_result['source_deleted'] = False
            copy_result['delete_error'] = str(e)
    
    return copy_result


def get_directory_size(path: Path) -> int:
    """Calculate total size of all files in a directory."""
    total = 0
    for entry in path.rglob('*'):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    size_float = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_float < 1024:
            return f"{size_float:.2f} {unit}"
        size_float /= 1024
    return f"{size_float:.2f} PB"


# ============================================================================
# PERMISSION CHECKING
# ============================================================================

def is_admin(user_id: str, config: Dict[str, Any]) -> bool:
    """
    Check if a Discord user ID is in the admin list.
    
    Args:
        user_id: Discord user ID as string
        config: Configuration dictionary
    
    Returns:
        True if user is an admin
    """
    admin_ids = config.get('discord', {}).get('admin_user_ids', [])
    return str(user_id) in [str(aid) for aid in admin_ids]
