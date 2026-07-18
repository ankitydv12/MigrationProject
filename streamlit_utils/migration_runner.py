import logging
from migration.parallel_migration import ParallelMigrationManager

logger = logging.getLogger(__name__)

def run_migration(
    progress_callback=None,
    status_callback=None,
    table_callback=None,
):
    """
    Run the migration using the new high-performance ParallelMigrationManager.
    """
    manager = ParallelMigrationManager()
    return manager.run(
        progress_callback=progress_callback,
        status_callback=status_callback,
        table_callback=table_callback
    )