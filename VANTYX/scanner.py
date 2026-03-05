"""
scanner.py - FL Studio File Scanner

This module scans directories for FL Studio project files and related assets.

Supported File Types:
- .flp  - FL Studio Project files
- .wav  - Audio files (samples, rendered audio)
- .mp3  - Compressed audio files
- .fst  - FL Studio State files (plugin presets)

Features:
- Recursive directory scanning
- File metadata collection (size, modified date)
- Results caching for performance
- Integration with audit logging
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
import json

from utils import AuditLogger, setup_logging, format_size

logger = setup_logging()


FL_STUDIO_EXTENSIONS = {'.flp', '.wav', '.mp3', '.fst'}


@dataclass
class ScannedFile:
    """Represents a scanned FL Studio file."""
    path: Path
    name: str
    extension: str
    size: int
    modified: datetime
    parent_folder: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'path': str(self.path),
            'name': self.name,
            'extension': self.extension,
            'size': self.size,
            'size_formatted': format_size(self.size),
            'modified': self.modified.isoformat(),
            'parent_folder': self.parent_folder
        }


@dataclass
class ScanResult:
    """Results from a directory scan."""
    scan_path: str
    scan_time: datetime
    total_files: int
    total_size: int
    files_by_type: Dict[str, List[ScannedFile]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'scan_path': self.scan_path,
            'scan_time': self.scan_time.isoformat(),
            'total_files': self.total_files,
            'total_size': self.total_size,
            'total_size_formatted': format_size(self.total_size),
            'files_by_type': {
                ext: [f.to_dict() for f in files]
                for ext, files in self.files_by_type.items()
            },
            'file_counts': {
                ext: len(files) for ext, files in self.files_by_type.items()
            },
            'errors': self.errors
        }
    
    def get_summary(self) -> str:
        """Get a human-readable summary of the scan."""
        lines = [
            f"Scan Results for: {self.scan_path}",
            f"Scanned at: {self.scan_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total files found: {self.total_files}",
            f"Total size: {format_size(self.total_size)}",
            "",
            "Files by type:"
        ]
        
        for ext, files in sorted(self.files_by_type.items()):
            total_ext_size = sum(f.size for f in files)
            lines.append(f"  {ext}: {len(files)} files ({format_size(total_ext_size)})")
        
        if self.errors:
            lines.append(f"\nErrors encountered: {len(self.errors)}")
        
        return '\n'.join(lines)


class FLStudioScanner:
    """
    Scanner for FL Studio files with caching and audit logging.
    
    This scanner:
    - Finds .flp, .wav, .mp3, .fst files
    - Collects file metadata
    - Caches results for quick re-access
    - Logs all scans to the audit system
    """
    
    def __init__(
        self,
        audit_logger: AuditLogger,
        cache_file: str = "scan_cache.json",
        extensions: Set[str] = None
    ):
        """
        Initialize the scanner.
        
        Args:
            audit_logger: AuditLogger instance
            cache_file: Path to cache file for scan results
            extensions: Set of file extensions to scan for
        """
        self.audit_logger = audit_logger
        self.cache_file = Path(cache_file)
        self.extensions = extensions or FL_STUDIO_EXTENSIONS
        self.last_scan: Optional[ScanResult] = None
        
        self._load_cache()
        
        logger.info(f"FL Studio Scanner initialized")
        logger.info(f"Scanning for extensions: {', '.join(self.extensions)}")
    
    def _load_cache(self) -> None:
        """Load cached scan results if available."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    logger.info(f"Loaded scan cache from {self.cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
    
    def _save_cache(self, result: ScanResult) -> None:
        """Save scan results to cache file."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, indent=2)
            logger.info(f"Saved scan cache to {self.cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def scan_directory(
        self,
        scan_path: str,
        user_id: str = None,
        user_name: str = None,
        max_depth: int = None
    ) -> ScanResult:
        """
        Scan a directory for FL Studio files.
        
        Args:
            scan_path: Path to directory to scan
            user_id: Discord user ID who initiated the scan
            user_name: Discord username
            max_depth: Maximum recursion depth (None for unlimited)
        
        Returns:
            ScanResult with all found files
        """
        path = Path(scan_path)
        result = ScanResult(
            scan_path=str(path),
            scan_time=datetime.now(),
            total_files=0,
            total_size=0
        )
        
        if not path.exists():
            result.errors.append(f"Path does not exist: {scan_path}")
            self._log_scan(result, user_id, user_name, success=False)
            return result
        
        if not path.is_dir():
            result.errors.append(f"Path is not a directory: {scan_path}")
            self._log_scan(result, user_id, user_name, success=False)
            return result
        
        logger.info(f"Starting scan of: {scan_path}")
        
        for ext in self.extensions:
            result.files_by_type[ext] = []
        
        try:
            self._scan_recursive(path, result, current_depth=0, max_depth=max_depth)
        except Exception as e:
            result.errors.append(f"Scan error: {str(e)}")
            logger.error(f"Scan error: {e}")
        
        self.last_scan = result
        self._save_cache(result)
        self._log_scan(result, user_id, user_name, success=True)
        
        logger.info(f"Scan complete: {result.total_files} files found")
        
        return result
    
    def _scan_recursive(
        self,
        directory: Path,
        result: ScanResult,
        current_depth: int,
        max_depth: Optional[int]
    ) -> None:
        """Recursively scan a directory."""
        if max_depth is not None and current_depth > max_depth:
            return
        
        try:
            entries = list(directory.iterdir())
        except PermissionError:
            result.errors.append(f"Permission denied: {directory}")
            return
        except Exception as e:
            result.errors.append(f"Error reading {directory}: {e}")
            return
        
        for entry in entries:
            try:
                if entry.is_dir():
                    self._scan_recursive(entry, result, current_depth + 1, max_depth)
                
                elif entry.is_file():
                    ext = entry.suffix.lower()
                    if ext in self.extensions:
                        stat = entry.stat()
                        
                        scanned_file = ScannedFile(
                            path=entry,
                            name=entry.name,
                            extension=ext,
                            size=stat.st_size,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            parent_folder=entry.parent.name
                        )
                        
                        result.files_by_type[ext].append(scanned_file)
                        result.total_files += 1
                        result.total_size += stat.st_size
                        
            except Exception as e:
                result.errors.append(f"Error processing {entry}: {e}")
    
    def _log_scan(
        self,
        result: ScanResult,
        user_id: str,
        user_name: str,
        success: bool
    ) -> None:
        """Log the scan operation to the audit system."""
        self.audit_logger.log_action(
            action_type='FILE_SCAN',
            success=success,
            dry_run=False,
            user_id=user_id,
            user_name=user_name,
            details=f"Scanned {result.scan_path}: {result.total_files} files found",
            source_path=result.scan_path,
            error_message='; '.join(result.errors) if result.errors else None
        )
    
    def find_flp_projects(
        self,
        scan_path: str = None,
        user_id: str = None,
        user_name: str = None
    ) -> List[ScannedFile]:
        """
        Find all FL Studio project files.
        
        If scan_path is provided, performs a new scan.
        Otherwise, uses cached results from the last scan.
        
        Args:
            scan_path: Optional path to scan (uses cache if None)
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            List of ScannedFile objects for .flp files
        """
        if scan_path:
            result = self.scan_directory(scan_path, user_id, user_name)
        elif self.last_scan:
            result = self.last_scan
        else:
            return []
        
        return result.files_by_type.get('.flp', [])
    
    def find_by_extension(
        self,
        extension: str,
        scan_path: str = None,
        user_id: str = None,
        user_name: str = None
    ) -> List[ScannedFile]:
        """
        Find all files with a specific extension.
        
        Args:
            extension: File extension (with or without dot)
            scan_path: Optional path to scan
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            List of matching ScannedFile objects
        """
        if not extension.startswith('.'):
            extension = '.' + extension
        
        extension = extension.lower()
        
        if extension not in self.extensions:
            logger.warning(f"Extension {extension} not in scan list")
            return []
        
        if scan_path:
            result = self.scan_directory(scan_path, user_id, user_name)
        elif self.last_scan:
            result = self.last_scan
        else:
            return []
        
        return result.files_by_type.get(extension, [])
    
    def find_large_files(
        self,
        min_size_mb: float = 100,
        scan_path: str = None,
        user_id: str = None,
        user_name: str = None
    ) -> List[ScannedFile]:
        """
        Find files larger than a specified size.
        
        Args:
            min_size_mb: Minimum file size in megabytes
            scan_path: Optional path to scan
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            List of large files sorted by size (descending)
        """
        if scan_path:
            result = self.scan_directory(scan_path, user_id, user_name)
        elif self.last_scan:
            result = self.last_scan
        else:
            return []
        
        min_size_bytes = min_size_mb * 1024 * 1024
        large_files = []
        
        for files in result.files_by_type.values():
            for f in files:
                if f.size >= min_size_bytes:
                    large_files.append(f)
        
        return sorted(large_files, key=lambda x: x.size, reverse=True)
    
    def search_by_name(
        self,
        pattern: str,
        scan_path: str = None,
        user_id: str = None,
        user_name: str = None
    ) -> List[ScannedFile]:
        """
        Search for files by name pattern (case-insensitive).
        
        Args:
            pattern: Search pattern (substring match)
            scan_path: Optional path to scan
            user_id: Discord user ID
            user_name: Discord username
        
        Returns:
            List of matching files
        """
        if scan_path:
            result = self.scan_directory(scan_path, user_id, user_name)
        elif self.last_scan:
            result = self.last_scan
        else:
            return []
        
        pattern_lower = pattern.lower()
        matches = []
        
        for files in result.files_by_type.values():
            for f in files:
                if pattern_lower in f.name.lower():
                    matches.append(f)
        
        return matches
    
    def get_last_scan_summary(self) -> Optional[str]:
        """Get a summary of the last scan, if available."""
        if self.last_scan:
            return self.last_scan.get_summary()
        return None
