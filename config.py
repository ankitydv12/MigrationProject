# MySQL to PostgreSQL Migration Configuration

# Thread pool configuration
# Maximum number of threads for parallel table processing
MAX_WORKERS = 8

# Batch/chunk size used for data extraction and loading operations
BATCH_SIZE = 5000

# Number of rows processed per streaming/chunked iteration
CHUNK_SIZE = 5000

# Feature flags
# Enable/disable row count validation step at the end of the migration
ENABLE_VALIDATION = True

# Enable/disable performance metrics summary display
ENABLE_PERFORMANCE_REPORT = True

# Enable/disable live console progress updates (e.g. "Completed X/Y tables")
ENABLE_PROGRESS_REPORT = True

# Timing & reporting options
# The number of tables to include in the slowest tables report section
TOP_SLOW_TABLE_COUNT = 5

# Database connection options
# Maximum time in seconds to wait for database connection before failing
CONNECTION_TIMEOUT = 30

# Application branding
# Header title used in console reports
APP_NAME = "MySQL to PostgreSQL Migration"

# Logging configuration
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = "INFO"

# Enable/disable writing logs to files
ENABLE_FILE_LOGGING = True

# Enable/disable printing logs to console
ENABLE_CONSOLE_LOGGING = True

# Directory where log files are stored
LOG_DIRECTORY = "logs"

# Global debug flag (when True, full stack traces are logged on error)
DEBUG = False

# Enable/disable using PostgreSQL COPY protocol for loading data
USE_POSTGRES_COPY = True

# Retry mechanism configuration
ENABLE_RETRY = True
MAX_RETRY_ATTEMPTS = 3
RETRY_INITIAL_DELAY = 1
RETRY_BACKOFF_FACTOR = 2

# Checkpoint & Resume configuration
ENABLE_CHECKPOINT = True
AUTO_RESUME = True
CHECKPOINT_FILE = "migration_checkpoint.json"
FORCE_FRESH_MIGRATION = False
