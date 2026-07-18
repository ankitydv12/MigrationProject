import os
import sys
import logging

# -------------------------------------------------
# Log Folder
# -------------------------------------------------

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "migration.log")


# -------------------------------------------------
# Custom File Handler (Flush Immediately)
# -------------------------------------------------

class FlushFileHandler(logging.FileHandler):

    def emit(self, record):
        super().emit(record)
        self.flush()


# -------------------------------------------------
# Capture Unhandled Exceptions
# -------------------------------------------------

def handle_exception(exc_type, exc_value, exc_traceback):

    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(
            exc_type,
            exc_value,
            exc_traceback
        )
        return

    logging.getLogger().error(
        "Unhandled Exception",
        exc_info=(
            exc_type,
            exc_value,
            exc_traceback
        )
    )


# -------------------------------------------------
# Setup Logging
# -------------------------------------------------

def setup_logging():

    os.makedirs(LOG_DIR, exist_ok=True)

    root_logger = logging.getLogger()

    # Remove old handlers (important for Streamlit reruns)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # -------------------------------------------------
    # File Handler
    # -------------------------------------------------

    file_handler = FlushFileHandler(
        LOG_FILE,
        mode="a",
        encoding="utf-8"
    )

    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    # -------------------------------------------------
    # Console Handler
    # -------------------------------------------------

    console_handler = logging.StreamHandler()

    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # -------------------------------------------------
    # Add Handlers
    # -------------------------------------------------

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # -------------------------------------------------
    # Capture Logs from Other Libraries
    # -------------------------------------------------

    logging.getLogger("sqlalchemy").setLevel(logging.INFO)
    logging.getLogger("mysql.connector").setLevel(loggingINFO if False else logging.INFO)
    logging.getLogger("psycopg2").setLevel(logging.INFO)
    logging.getLogger("streamlit").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # -------------------------------------------------
    # Capture Unhandled Exceptions
    # -------------------------------------------------

    sys.excepthook = handle_exception

    root_logger.info("=" * 70)
    root_logger.info("Logging Started")
    root_logger.info("=" * 70)

    return root_logger