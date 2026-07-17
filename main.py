import sys
import os

# Limit OpenBLAS and other linear algebra libraries to single thread to prevent memory allocation crashes in thread workers
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

from migration.parallel_migration import ParallelMigrationManager

def main():
    manager = ParallelMigrationManager()
    manager.run()

if __name__ == "__main__":
    main()