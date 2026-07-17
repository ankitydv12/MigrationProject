import os
import logging
from datetime import datetime
import config

_logger_configured = False

class MigrationFormatter(logging.Formatter):
    def __init__(self, migration_id, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)
        self.migration_id = migration_id

    def format(self, record):
        record.migration_id = self.migration_id
        return super().format(record)

def setup_logger(migration_id):
    """
    Configures and returns the dedicated "migration" logger.
    Ensures that the logger configuration is performed only once.
    
    :param migration_id: Unique identifier for the current migration run.
    """
    global _logger_configured
    logger = logging.getLogger("migration")
    
    # Configure the log level based on config
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Avoid adding handlers again if the logger has already been configured
    if _logger_configured or logger.handlers:
        return logger
        
    formatter = MigrationFormatter(
        migration_id=migration_id,
        fmt="Migration=%(migration_id)s | %(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Configure Console Logging handler
    if config.ENABLE_CONSOLE_LOGGING:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        logger.addHandler(console_handler)
        
    # Configure File Logging handler
    if config.ENABLE_FILE_LOGGING:
        log_dir = config.LOG_DIRECTORY
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"migration_{migration_id}.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        logger.addHandler(file_handler)
        
    _logger_configured = True
    return logger
