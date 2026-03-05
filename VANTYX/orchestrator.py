"""
orchestrator.py - Workflow Orchestrator and Approval System

This module coordinates all agent operations and manages the approval workflow.

Key Responsibilities:
- Coordinate between scanner, VMware controller, and backup system
- Manage approval requests for destructive actions
- Execute approved operations
- Handle backup operations with verification

Security Design:
- All destructive actions require Discord approval
- Operations are logged to audit system
- Dry-run mode prevents accidental changes
"""

import asyncio
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from utils import (
    AuditLogger, 
    setup_logging, 
    safe_copy_file, 
    safe_move_file,
    format_size,
    calculate_file_hash
)
from scanner import FLStudioScanner, ScannedFile
from vmware_controller import VMwareController

logger = setup_logging()


class ActionType(Enum):
    """Types of actions that can be requested."""
    FILE_MOVE = "file_move"
    FILE_BACKUP = "file_backup"
    FILE_DELETE = "file_delete"
    VM_START = "vm_start"
    VM_STOP = "vm_stop"
    VM_SNAPSHOT_CREATE = "vm_snapshot_create"
    VM_SNAPSHOT_REVERT = "vm_snapshot_revert"
    BACKUP_PROJECT = "backup_project"
    BULK_BACKUP = "bulk_backup"


@dataclass
class PendingAction:
    """Represents an action waiting for approval."""
    id: int
    action_type: ActionType
    requested_by: str
    requested_by_name: str
    details: str
    source_path: Optional[str]
    dest_path: Optional[str]
    extra_data: Dict[str, Any]
    created_at: datetime


class BackupManager:
    """
    Manages backup operations for FL Studio projects.
    
    Features:
    - Copy projects to backup folder
    - Verify backups with hash comparison
    - Organize backups by date
    - Track backup history
    """
    
    def __init__(
        self,
        backup_root: str,
        audit_logger: AuditLogger,
        dry_run: bool = True
    ):
        """
        Initialize the backup manager.
        
        Args:
            backup_root: Root directory for backups
            audit_logger: AuditLogger instance
            dry_run: If True, simulate operations
        """
        self.backup_root = Path(backup_root)
        self.audit_logger = audit_logger
        self.dry_run = dry_run
        
        logger.info(f"Backup manager initialized. Root: {self.backup_root}")
        logger.info(f"Dry-run mode: {self.dry_run}")
    
    def _get_backup_folder(self) -> Path:
        """Get today's backup folder path."""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.backup_root / today
    
    async def backup_file(
        self,
        source_file: Path,
        user_id: str = None,
        user_name: str = None,
        preserve_structure: bool = True
    ) -> Dict[str, Any]:
        """
        Backup a single file to the backup folder.
        
        Args:
            source_file: Path to the file to backup
            user_id: Discord user ID
            user_name: Discord username
            preserve_structure: If True, maintain relative folder structure
        
        Returns:
            Operation result dictionary
        """
        source = Path(source_file)
        backup_folder = self._get_backup_folder()
        
        if preserve_structure:
            dest = backup_folder / source.parent.name / source.name
        else:
            dest = backup_folder / source.name
        
        counter = 1
        original_dest = dest
        while dest.exists() and not self.dry_run:
            stem = original_dest.stem
            suffix = original_dest.suffix
            dest = original_dest.parent / f"{stem}_{counter}{suffix}"
            counter += 1
        
        result = safe_copy_file(source, dest, verify=True, dry_run=self.dry_run)
        
        self.audit_logger.log_action(
            action_type='FILE_BACKUP',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Backup file to {dest}",
            source_path=str(source),
            dest_path=str(dest),
            error_message=result.get('error')
        )
        
        return result
    
    async def backup_project(
        self,
        project_path: Path,
        include_samples: bool = True,
        user_id: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """
        Backup an FL Studio project and its related files.
        
        This backs up the .flp file and optionally scans for
        related audio files in the same directory.
        
        Args:
            project_path: Path to the .flp file
            include_samples: If True, also backup .wav/.mp3 in same folder
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            Operation result with list of backed up files
        """
        result = {
            'success': False,
            'project': str(project_path),
            'backed_up_files': [],
            'total_size': 0,
            'dry_run': self.dry_run,
            'errors': []
        }
        
        project = Path(project_path)
        
        if not project.exists():
            result['errors'].append(f"Project not found: {project}")
            return result
        
        project_result = await self.backup_file(project, user_id, user_name)
        if project_result['success']:
            result['backed_up_files'].append(str(project))
            result['total_size'] += project.stat().st_size if project.exists() else 0
        else:
            result['errors'].append(project_result.get('error', 'Unknown error'))
        
        if include_samples:
            project_dir = project.parent
            sample_extensions = {'.wav', '.mp3', '.fst'}
            
            for file in project_dir.iterdir():
                if file.suffix.lower() in sample_extensions:
                    file_result = await self.backup_file(file, user_id, user_name)
                    if file_result['success']:
                        result['backed_up_files'].append(str(file))
                        result['total_size'] += file.stat().st_size if file.exists() else 0
                    else:
                        result['errors'].append(f"{file.name}: {file_result.get('error')}")
        
        result['success'] = len(result['backed_up_files']) > 0
        result['total_size_formatted'] = format_size(result['total_size'])
        
        self.audit_logger.log_action(
            action_type='BACKUP_PROJECT',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Backed up {len(result['backed_up_files'])} files ({result['total_size_formatted']})",
            source_path=str(project),
            error_message='; '.join(result['errors']) if result['errors'] else None
        )
        
        return result
    
    async def bulk_backup(
        self,
        files: List[ScannedFile],
        user_id: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """
        Backup multiple files at once.
        
        Args:
            files: List of ScannedFile objects to backup
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            Bulk operation result
        """
        result = {
            'success': False,
            'total_files': len(files),
            'backed_up': 0,
            'failed': 0,
            'total_size': 0,
            'dry_run': self.dry_run,
            'errors': []
        }
        
        for scanned_file in files:
            file_result = await self.backup_file(
                scanned_file.path, user_id, user_name
            )
            
            if file_result['success']:
                result['backed_up'] += 1
                result['total_size'] += scanned_file.size
            else:
                result['failed'] += 1
                result['errors'].append(f"{scanned_file.name}: {file_result.get('error')}")
        
        result['success'] = result['backed_up'] > 0
        result['total_size_formatted'] = format_size(result['total_size'])
        
        self.audit_logger.log_action(
            action_type='BULK_BACKUP',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Bulk backup: {result['backed_up']}/{result['total_files']} files ({result['total_size_formatted']})",
            error_message='; '.join(result['errors'][:5]) if result['errors'] else None
        )
        
        return result


class Orchestrator:
    """
    Main orchestrator that coordinates all agent operations.
    
    This class:
    - Manages pending approval requests
    - Coordinates between scanner, VMware, and backup systems
    - Executes approved operations
    - Enforces dry-run mode globally
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        audit_logger: AuditLogger,
        scanner: FLStudioScanner,
        vmware_controller: Optional[VMwareController],
        backup_manager: BackupManager
    ):
        """
        Initialize the orchestrator.
        
        Args:
            config: Configuration dictionary
            audit_logger: AuditLogger instance
            scanner: FLStudioScanner instance
            vmware_controller: VMwareController instance (optional)
            backup_manager: BackupManager instance
        """
        self.config = config
        self.audit_logger = audit_logger
        self.scanner = scanner
        self.vmware_controller = vmware_controller
        self.backup_manager = backup_manager
        self.dry_run = config.get('agent', {}).get('dry_run', True)
        
        self.pending_actions: Dict[int, PendingAction] = {}
        
        self._load_pending_approvals()
        
        logger.info("Orchestrator initialized")
        logger.info(f"Global dry-run mode: {self.dry_run}")
    
    def _load_pending_approvals(self) -> None:
        """Load pending approvals from database."""
        pending = self.audit_logger.get_pending_approvals()
        for p in pending:
            try:
                action = PendingAction(
                    id=p['id'],
                    action_type=ActionType(p['action_type'].lower()),
                    requested_by=p['requested_by'],
                    requested_by_name='',
                    details=p['details'],
                    source_path=p.get('source_path'),
                    dest_path=p.get('dest_path'),
                    extra_data={},
                    created_at=datetime.fromisoformat(p['created_at'])
                )
                self.pending_actions[action.id] = action
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to load pending approval {p.get('id')}: {e}")
        
        logger.info(f"Loaded {len(self.pending_actions)} pending approvals")
    
    def request_approval(
        self,
        action_type: ActionType,
        requested_by: str,
        requested_by_name: str,
        details: str,
        source_path: Optional[str] = None,
        dest_path: Optional[str] = None,
        extra_data: Dict[str, Any] = None
    ) -> PendingAction:
        """
        Create a new approval request.
        
        Args:
            action_type: Type of action
            requested_by: Discord user ID
            requested_by_name: Discord username
            details: Description of the action
            source_path: Source file/VM path
            dest_path: Destination path
            extra_data: Additional data for the action
        
        Returns:
            The created PendingAction
        """
        request_id = self.audit_logger.create_approval_request(
            action_type=action_type.value,
            requested_by=requested_by,
            details=details,
            source_path=source_path,
            dest_path=dest_path
        )
        
        action = PendingAction(
            id=request_id,
            action_type=action_type,
            requested_by=requested_by,
            requested_by_name=requested_by_name,
            details=details,
            source_path=source_path,
            dest_path=dest_path,
            extra_data=extra_data or {},
            created_at=datetime.now()
        )
        
        self.pending_actions[request_id] = action
        
        logger.info(f"Created approval request #{request_id}: {action_type.value}")
        
        return action
    
    def approve_action(
        self,
        request_id: int,
        approved_by: str
    ) -> bool:
        """
        Approve a pending action.
        
        Args:
            request_id: The approval request ID
            approved_by: Discord user ID of approver
        
        Returns:
            True if approval was successful
        """
        if request_id not in self.pending_actions:
            logger.warning(f"Approval request #{request_id} not found")
            return False
        
        success = self.audit_logger.approve_request(request_id, approved_by)
        
        if success:
            logger.info(f"Approval request #{request_id} approved by {approved_by}")
        
        return success
    
    def deny_action(self, request_id: int) -> bool:
        """
        Deny/cancel a pending action.
        
        Args:
            request_id: The approval request ID
        
        Returns:
            True if denial was successful
        """
        if request_id in self.pending_actions:
            del self.pending_actions[request_id]
            logger.info(f"Approval request #{request_id} denied/cancelled")
            return True
        return False
    
    def get_pending_actions(self) -> List[PendingAction]:
        """Get all pending approval requests."""
        return list(self.pending_actions.values())
    
    async def execute_approved_actions(
        self,
        user_id: str = None,
        user_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Execute all approved but not yet executed actions.
        
        Returns:
            List of execution results
        """
        approved = self.audit_logger.get_approved_unexecuted()
        results = []
        
        for approval in approved:
            try:
                result = await self._execute_action(approval, user_id, user_name)
                results.append(result)
                
                if result['success']:
                    self.audit_logger.mark_executed(approval['id'])
                    if approval['id'] in self.pending_actions:
                        del self.pending_actions[approval['id']]
                        
            except Exception as e:
                logger.error(f"Error executing action #{approval['id']}: {e}")
                results.append({
                    'id': approval['id'],
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    async def _execute_action(
        self,
        approval: Dict[str, Any],
        user_id: str,
        user_name: str
    ) -> Dict[str, Any]:
        """Execute a single approved action."""
        action_type = approval['action_type'].lower()
        result = {'id': approval['id'], 'action_type': action_type}
        
        try:
            if action_type == ActionType.FILE_BACKUP.value:
                source = Path(approval['source_path'])
                backup_result = await self.backup_manager.backup_file(
                    source, user_id, user_name
                )
                result.update(backup_result)
                
            elif action_type == ActionType.FILE_MOVE.value:
                source = Path(approval['source_path'])
                dest = Path(approval['dest_path'])
                move_result = safe_move_file(source, dest, dry_run=self.dry_run)
                result.update(move_result)
                
            elif action_type == ActionType.VM_START.value and self.vmware_controller:
                vm_name = approval.get('details', '').split("'")[1] if "'" in approval.get('details', '') else ''
                vm_result = await self.vmware_controller.start_vm(
                    vm_name, user_id, user_name
                )
                result.update(vm_result)
                
            elif action_type == ActionType.VM_STOP.value and self.vmware_controller:
                vm_name = approval.get('details', '').split("'")[1] if "'" in approval.get('details', '') else ''
                vm_result = await self.vmware_controller.stop_vm(
                    vm_name, user_id, user_name
                )
                result.update(vm_result)
                
            else:
                result['success'] = False
                result['error'] = f"Unknown action type: {action_type}"
                
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
        
        return result
    
    async def quick_scan(
        self,
        scan_path: str,
        user_id: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """
        Perform a quick scan of a directory.
        
        Args:
            scan_path: Path to scan
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            Scan results
        """
        result = self.scanner.scan_directory(scan_path, user_id, user_name)
        return result.to_dict()
    
    async def backup_all_projects(
        self,
        scan_path: str,
        user_id: str = None,
        user_name: str = None,
        require_approval: bool = True
    ) -> Dict[str, Any]:
        """
        Backup all FL Studio projects in a directory.
        
        Args:
            scan_path: Path to scan for projects
            user_id: Discord user ID
            user_name: Discord username
            require_approval: If True, create approval request first
        
        Returns:
            Operation result or approval request info
        """
        projects = self.scanner.find_flp_projects(scan_path, user_id, user_name)
        
        if not projects:
            return {
                'success': False,
                'message': 'No FL Studio projects found'
            }
        
        total_size = sum(p.size for p in projects)
        
        if require_approval:
            action = self.request_approval(
                action_type=ActionType.BULK_BACKUP,
                requested_by=user_id or 'system',
                requested_by_name=user_name or 'System',
                details=f"Backup {len(projects)} projects ({format_size(total_size)})",
                source_path=scan_path
            )
            
            return {
                'success': True,
                'approval_required': True,
                'request_id': action.id,
                'project_count': len(projects),
                'total_size': format_size(total_size),
                'message': f"Approval request #{action.id} created. Waiting for admin approval."
            }
        
        return await self.backup_manager.bulk_backup(projects, user_id, user_name)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current system status."""
        status = {
            'dry_run': self.dry_run,
            'pending_approvals': len(self.pending_actions),
            'scanner': {
                'last_scan': self.scanner.get_last_scan_summary()
            },
            'vmware': {
                'enabled': self.vmware_controller is not None,
                'configured_vms': (
                    self.vmware_controller.list_configured_vms()
                    if self.vmware_controller else []
                )
            }
        }
        
        return status
