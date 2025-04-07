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
        self.json_log_file = self.log_dir / "file_operations.json"
        
        # Initialize JSON log if it doesn't exist
        if not self.json_log_file.exists():
            with open(self.json_log_file, 'w') as f:
                json.dump([], f)
    
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
        
        # Log to JSON file
        try:
            with open(self.json_log_file, 'r') as f:
                log_data = json.load(f)
            
            log_data.append(log_entry)
            
            with open(self.json_log_file, 'w') as f:
                json.dump(log_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing to JSON log: {e}")
    
    def get_recent_operations(self, limit: int = 50) -> List[Dict]:
        """Get recent file operations.
        
        Args:
            limit: Maximum number of operations to return
            
        Returns:
            List of recent operations
        """
        try:
            with open(self.json_log_file, 'r') as f:
                log_data = json.load(f)
            
            # Sort by timestamp (newest first) and limit
            sorted_data = sorted(log_data, key=lambda x: x["timestamp"], reverse=True)
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
            with open(self.json_log_file, 'r') as f:
                log_data = json.load(f)
            
            # Filter operations for this file (either as source or target)
            file_operations = [
                op for op in log_data 
                if op["source_file"] == file_path or op["target_file"] == file_path
            ]
            
            # Sort by timestamp (newest first)
            return sorted(file_operations, key=lambda x: x["timestamp"], reverse=True)
        except Exception as e:
            logger.error(f"Error reading JSON log: {e}")
            return []
