import sys
import os
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from migration.parallel_migration import ParallelMigrationManager

def main():
    manager = ParallelMigrationManager()
    manager.run()

if __name__ == "__main__":
    main()