"""
vmware_controller.py - VMware Workstation Controller

This module provides safe control of VMware virtual machines using vmrun.exe.

Supported Operations:
- Start/Stop VMs
- Suspend/Resume VMs
- Create/Revert snapshots
- Get VM status

Security Notes:
- Only predefined VMX paths from config are allowed
- No arbitrary paths or commands accepted
- All operations are logged to the audit system
- Destructive operations require Discord approval
"""

import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

from utils import AuditLogger, setup_logging

logger = setup_logging()


class VMPowerState(Enum):
    """Possible VM power states."""
    RUNNING = "running"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


@dataclass
class VMInfo:
    """Information about a configured VM."""
    name: str
    vmx_path: str
    description: str = ""


class VMwareController:
    """
    Controller for VMware Workstation VMs via vmrun.exe.
    
    This class provides a safe interface to VMware operations:
    - Only VMs defined in config can be controlled
    - All operations are logged
    - Dry-run mode prevents actual changes during testing
    """
    
    def __init__(
        self,
        vmrun_path: str,
        vms_config: List[Dict[str, str]],
        audit_logger: AuditLogger,
        dry_run: bool = True
    ):
        """
        Initialize the VMware controller.
        
        Args:
            vmrun_path: Path to vmrun.exe
            vms_config: List of VM configurations from agent_config.yaml
            audit_logger: AuditLogger instance for logging operations
            dry_run: If True, simulate operations without executing
        """
        self.vmrun_path = Path(vmrun_path)
        self.audit_logger = audit_logger
        self.dry_run = dry_run
        
        self.vms: Dict[str, VMInfo] = {}
        for vm in vms_config:
            name = vm.get('name', '').lower()
            if name:
                self.vms[name] = VMInfo(
                    name=name,
                    vmx_path=vm.get('vmx_path', ''),
                    description=vm.get('description', '')
                )
        
        logger.info(f"VMware controller initialized with {len(self.vms)} VMs")
        logger.info(f"Dry-run mode: {self.dry_run}")
    
    def _validate_vm_name(self, vm_name: str) -> Optional[VMInfo]:
        """
        Validate that a VM name exists in the configuration.
        
        Security: This prevents arbitrary VMX paths from being used.
        
        Args:
            vm_name: Name of the VM to validate
        
        Returns:
            VMInfo if valid, None otherwise
        """
        return self.vms.get(vm_name.lower())
    
    async def _run_vmrun(
        self,
        command: str,
        vmx_path: str,
        extra_args: List[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a vmrun command safely.
        
        Args:
            command: vmrun command (start, stop, suspend, etc.)
            vmx_path: Path to the VMX file
            extra_args: Additional arguments for the command
        
        Returns:
            Dictionary with command results
        """
        result = {
            'success': False,
            'command': command,
            'vmx_path': vmx_path,
            'dry_run': self.dry_run,
            'output': '',
            'error': None
        }
        
        if not self.vmrun_path.exists():
            result['error'] = f"vmrun.exe not found at: {self.vmrun_path}"
            return result
        
        if not Path(vmx_path).exists():
            result['error'] = f"VMX file not found: {vmx_path}"
            return result
        
        args = [str(self.vmrun_path), '-T', 'ws', command, vmx_path]
        if extra_args:
            args.extend(extra_args)
        
        if self.dry_run:
            result['success'] = True
            result['output'] = f"[DRY-RUN] Would execute: {' '.join(args)}"
            logger.info(result['output'])
            return result
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            result['output'] = stdout.decode('utf-8', errors='ignore').strip()
            
            if process.returncode == 0:
                result['success'] = True
            else:
                result['error'] = stderr.decode('utf-8', errors='ignore').strip()
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"vmrun error: {e}")
        
        return result
    
    async def start_vm(
        self,
        vm_name: str,
        user_id: str = None,
        user_name: str = None,
        gui: bool = True
    ) -> Dict[str, Any]:
        """
        Start a virtual machine.
        
        Args:
            vm_name: Name of the VM (from config)
            user_id: Discord user ID who initiated the action
            user_name: Discord username
            gui: If True, start with GUI; if False, headless
        
        Returns:
            Operation result dictionary
        """
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return {
                'success': False,
                'error': f"Unknown VM: {vm_name}. Available: {list(self.vms.keys())}"
            }
        
        mode = 'gui' if gui else 'nogui'
        result = await self._run_vmrun('start', vm.vmx_path, [mode])
        
        self.audit_logger.log_action(
            action_type='VM_START',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Started VM '{vm_name}' in {mode} mode",
            source_path=vm.vmx_path,
            error_message=result.get('error')
        )
        
        return result
    
    async def stop_vm(
        self,
        vm_name: str,
        user_id: str = None,
        user_name: str = None,
        hard: bool = False
    ) -> Dict[str, Any]:
        """
        Stop a virtual machine.
        
        Args:
            vm_name: Name of the VM
            user_id: Discord user ID
            user_name: Discord username
            hard: If True, force stop; if False, graceful shutdown
        
        Returns:
            Operation result dictionary
        """
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return {
                'success': False,
                'error': f"Unknown VM: {vm_name}"
            }
        
        command = 'stop'
        extra_args = ['hard'] if hard else ['soft']
        
        result = await self._run_vmrun(command, vm.vmx_path, extra_args)
        
        self.audit_logger.log_action(
            action_type='VM_STOP',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Stopped VM '{vm_name}' ({'hard' if hard else 'soft'})",
            source_path=vm.vmx_path,
            error_message=result.get('error')
        )
        
        return result
    
    async def suspend_vm(
        self,
        vm_name: str,
        user_id: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """Suspend a virtual machine."""
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return {'success': False, 'error': f"Unknown VM: {vm_name}"}
        
        result = await self._run_vmrun('suspend', vm.vmx_path)
        
        self.audit_logger.log_action(
            action_type='VM_SUSPEND',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Suspended VM '{vm_name}'",
            source_path=vm.vmx_path,
            error_message=result.get('error')
        )
        
        return result
    
    async def create_snapshot(
        self,
        vm_name: str,
        snapshot_name: str,
        user_id: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """
        Create a snapshot of a virtual machine.
        
        Args:
            vm_name: Name of the VM
            snapshot_name: Name for the new snapshot
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            Operation result dictionary
        """
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return {'success': False, 'error': f"Unknown VM: {vm_name}"}
        
        safe_snapshot_name = ''.join(
            c for c in snapshot_name if c.isalnum() or c in ' _-'
        )[:50]
        
        result = await self._run_vmrun('snapshot', vm.vmx_path, [safe_snapshot_name])
        
        self.audit_logger.log_action(
            action_type='VM_SNAPSHOT_CREATE',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Created snapshot '{safe_snapshot_name}' for VM '{vm_name}'",
            source_path=vm.vmx_path,
            error_message=result.get('error')
        )
        
        return result
    
    async def revert_snapshot(
        self,
        vm_name: str,
        snapshot_name: str,
        user_id: str = None,
        user_name: str = None
    ) -> Dict[str, Any]:
        """
        Revert a VM to a previous snapshot.
        
        WARNING: This is a destructive operation and requires approval.
        
        Args:
            vm_name: Name of the VM
            snapshot_name: Name of the snapshot to revert to
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            Operation result dictionary
        """
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return {'success': False, 'error': f"Unknown VM: {vm_name}"}
        
        result = await self._run_vmrun('revertToSnapshot', vm.vmx_path, [snapshot_name])
        
        self.audit_logger.log_action(
            action_type='VM_SNAPSHOT_REVERT',
            success=result['success'],
            dry_run=self.dry_run,
            user_id=user_id,
            user_name=user_name,
            details=f"Reverted VM '{vm_name}' to snapshot '{snapshot_name}'",
            source_path=vm.vmx_path,
            error_message=result.get('error')
        )
        
        return result
    
    async def list_snapshots(self, vm_name: str) -> Dict[str, Any]:
        """List all snapshots for a VM."""
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return {'success': False, 'error': f"Unknown VM: {vm_name}"}
        
        result = await self._run_vmrun('listSnapshots', vm.vmx_path)
        
        if result['success'] and result['output']:
            lines = result['output'].split('\n')
            result['snapshots'] = [
                line.strip() for line in lines[1:] if line.strip()
            ]
        
        return result
    
    async def get_running_vms(self) -> Dict[str, Any]:
        """Get a list of currently running VMs."""
        result = {
            'success': False,
            'running_vms': [],
            'dry_run': self.dry_run,
            'error': None
        }
        
        if not self.vmrun_path.exists():
            result['error'] = f"vmrun.exe not found at: {self.vmrun_path}"
            return result
        
        if self.dry_run:
            result['success'] = True
            result['output'] = "[DRY-RUN] Would list running VMs"
            return result
        
        try:
            process = await asyncio.create_subprocess_exec(
                str(self.vmrun_path), 'list',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode('utf-8', errors='ignore')
                lines = output.strip().split('\n')
                
                result['running_vms'] = [
                    line.strip() for line in lines[1:] if line.strip()
                ]
                result['success'] = True
            else:
                result['error'] = stderr.decode('utf-8', errors='ignore')
                
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def get_vm_status(self, vm_name: str, running_vms: List[str]) -> VMPowerState:
        """
        Determine the power state of a VM.
        
        Args:
            vm_name: Name of the VM
            running_vms: List of running VMX paths from get_running_vms()
        
        Returns:
            VMPowerState enum value
        """
        vm = self._validate_vm_name(vm_name)
        if not vm:
            return VMPowerState.UNKNOWN
        
        vmx_path_lower = vm.vmx_path.lower()
        for running_path in running_vms:
            if running_path.lower() == vmx_path_lower:
                return VMPowerState.RUNNING
        
        return VMPowerState.STOPPED
    
    def list_configured_vms(self) -> List[Dict[str, str]]:
        """Get list of all configured VMs."""
        return [
            {
                'name': vm.name,
                'vmx_path': vm.vmx_path,
                'description': vm.description
            }
            for vm in self.vms.values()
        ]
