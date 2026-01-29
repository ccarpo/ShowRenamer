"""File logger module for tracking file changes."""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

class FileLogger:
    """Logger for tracking file operations."""
    
    def __init__(self, log_dir: str = None):
        """Initialize the file logger.
        
        Args:
            log_dir: Directory to store log files. Defaults to config_dir/logs.
        """
        if log_dir is None:
            # Use default log directory in config
            from showrenamer.config import Config
            config = Config()
            log_dir = os.path.join(config.config_dir, "logs")
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "file_operations.log"
        self.json_log_file = self.log_dir / "file_operations.jsonl"  # JSONL format (JSON Lines)
        self.max_log_size = 10 * 1024 * 1024  # 10MB max size before rotation
        
        # Create empty JSONL file if it doesn't exist
        if not self.json_log_file.exists():
            self.json_log_file.touch()
    
    def log_operation(self, 
                      operation_type: str, 
                      source_file: Union[str, Path], 
                      target_file: Optional[Union[str, Path]] = None,
                      success: bool = True,
                      details: Optional[Dict] = None) -> None:
        """Log a file operation.
        
        Args:
            operation_type: Type of operation (rename, move, etc.)
            source_file: Source file path
            target_file: Target file path (for rename/move operations)
            success: Whether the operation was successful
            details: Additional details about the operation
        """
        timestamp = datetime.now().isoformat()
        source_file = str(source_file)
        target_file = str(target_file) if target_file else None
        
        # Create log entry
        log_entry = {
            "timestamp": timestamp,
            "operation": operation_type,
            "source_file": source_file,
            "target_file": target_file,
            "success": success,
            "details": details or {}
        }
        
        # Log to text file
        with open(self.log_file, 'a') as f:
            status = "SUCCESS" if success else "FAILED"
            target_info = f" -> {target_file}" if target_file else ""
            f.write(f"{timestamp} - {operation_type.upper()} {status}: {source_file}{target_info}\n")
            if details:
                f.write(f"  Details: {json.dumps(details)}\n")
        
        # Log to JSONL file (append-only, one JSON object per line)
        try:
            # Check if rotation is needed
            if self.json_log_file.exists() and self.json_log_file.stat().st_size > self.max_log_size:
                self._rotate_log()
            
            # Append the log entry as a single line
            with open(self.json_log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Error writing to JSON log: {e}")
    
    def _rotate_log(self):
        """Rotate the log file when it gets too large."""
        try:
            # Rename current log to .old
            old_log = self.log_dir / "file_operations.old.jsonl"
            if old_log.exists():
                old_log.unlink()  # Delete the old backup
            self.json_log_file.rename(old_log)
            # Create new empty log
            self.json_log_file.touch()
            logger.info(f"Rotated log file. Old log saved to {old_log}")
        except Exception as e:
            logger.error(f"Error rotating log file: {e}")
    
    def get_recent_operations(self, limit: int = 50) -> List[Dict]:
        """Get recent file operations.
        
        Args:
            limit: Maximum number of operations to return
            
        Returns:
            List of recent operations
        """
        try:
            log_data = []
            if self.json_log_file.exists():
                with open(self.json_log_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                log_data.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue  # Skip corrupted lines
            
            # Sort by timestamp (newest first) and limit
            sorted_data = sorted(log_data, key=lambda x: x.get("timestamp", ""), reverse=True)
            return sorted_data[:limit]
        except Exception as e:
            logger.error(f"Error reading JSON log: {e}")
            return []
    
    def get_operations_for_file(self, file_path: Union[str, Path]) -> List[Dict]:
        """Get all operations for a specific file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of operations for the file
        """
        file_path = str(file_path)
        try:
            log_data = []
            if self.json_log_file.exists():
                with open(self.json_log_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                log_data.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue  # Skip corrupted lines
            
            # Filter operations for this file (either as source or target)
            file_operations = [
                op for op in log_data 
                if op.get("source_file") == file_path or op.get("target_file") == file_path
            ]
            
            # Sort by timestamp (newest first)
            return sorted(file_operations, key=lambda x: x.get("timestamp", ""), reverse=True)
        except Exception as e:
            logger.error(f"Error reading JSON log: {e}")
            return []
