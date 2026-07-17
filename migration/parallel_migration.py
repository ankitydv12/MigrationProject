import sys
import os
import logging
import time
import concurrent.futures

# Ensure the project root is in the Python search path.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.schema_analyzer import analyze_schema
from migration.extract import extract_table_data, get_table_schema
from migration.transformer import transform_table
from migration.loader import load_table, add_foreign_keys
from validation.Validate import run_validation
from config.db_config import get_postgres_connection

logger = logging.getLogger(__name__)

class ParallelMigrationManager:
    def __init__(self, max_workers=8):
        """
        Initialize the ParallelMigrationManager.
        
        :param max_workers: The maximum number of threads in the ThreadPoolExecutor (default: 8).
        """
        self.schema_info = None
        self.max_workers = max_workers

    def _analyze_schema(self):
        """
        Analyze schema once at the start of the pipeline.
        """
        return analyze_schema()

    def _extract(self, table_name):
        """
        Extract data from MySQL for a single table.
        """
        return extract_table_data(table_name)

    def _transform(self, df, table_name):
        """
        Transform MySQL data to PostgreSQL-compatible formats for a single table.
        """
        return transform_table(df, table_name, self.schema_info)

    def _load(self, pg_conn, table_name, df, schema):
        """
        Load transformed data to PostgreSQL for a single table.
        """
        return load_table(pg_conn, table_name, df, schema, self.schema_info)

    def _validate(self):
        """
        Validate the migration by comparing row counts.
        """
        return run_validation()

    def _process_table(self, table_name):
        """
        Coordinates the table-processing workflow for a single table:
        Creates a dedicated PostgreSQL connection, disables FK enforcement for that session,
        executes the table-processing ETL stages, restores FK enforcement, and closes the connection.
        """
        start_time = time.perf_counter()
        pg_conn = None
        fk_disabled = False
        try:
            # 1. Create connection
            pg_conn = get_postgres_connection()
            
            # 2. Disable FK enforcement on this connection/session
            cursor = pg_conn.cursor()
            cursor.execute("SET session_replication_role = replica;")
            pg_conn.commit()
            cursor.close()
            fk_disabled = True
            logger.info(f"[{table_name}] FK constraints disabled for bulk load")

            # 3. Coordinate stages
            df = self._extract(table_name)
            schema = get_table_schema(table_name)
            transformed_df = self._transform(df, table_name)
            rows = self._load(pg_conn, table_name, transformed_df, schema)

            # 4. Restore FK enforcement on this connection/session
            cursor = pg_conn.cursor()
            cursor.execute("SET session_replication_role = DEFAULT;")
            pg_conn.commit()
            cursor.close()
            fk_disabled = False
            logger.info(f"[{table_name}] FK constraints re-enabled")

            duration = time.perf_counter() - start_time
            return {
                "table": table_name,
                "success": True,
                "rows": rows,
                "duration": duration
            }
        except Exception as e:
            duration = time.perf_counter() - start_time
            logger.error(f"[{table_name}] Failed to migrate table: {e}")
            return {
                "table": table_name,
                "success": False,
                "rows": 0,
                "duration": duration,
                "error": str(e)
            }
        finally:
            if pg_conn:
                if fk_disabled:
                    try:
                        cursor = pg_conn.cursor()
                        cursor.execute("SET session_replication_role = DEFAULT;")
                        pg_conn.commit()
                        cursor.close()
                        logger.info(f"[{table_name}] FK constraints re-enabled in finally block")
                    except Exception as ex:
                        logger.error(f"[{table_name}] Failed to restore FK constraints in finally block: {ex}")
                pg_conn.close()

    def run(self):
        """
        Run the complete migration pipeline in parallel using a ThreadPoolExecutor.
        """
        pipeline_start = time.perf_counter()

        print("\n" + "="*50)
        print("MYSQL TO POSTGRESQL MIGRATION PIPELINE")
        print("="*50)

        # 1. Analyze Schema
        self.schema_info = self._analyze_schema()

        # Print summary of what was auto-detected
        print("\n=== AUTO-DETECTED SCHEMA SUMMARY ===")
        print(f"Total tables found           : {len(self.schema_info['migration_order'])}")
        print(f"Total FK relationships       : {len(self.schema_info['foreign_keys'])}")
        print(f"UUID tables detected         : {len(self.schema_info['uuid_tables'])} {self.schema_info['uuid_tables']}")
        print(f"JSON column tables detected  : {len(self.schema_info['json_columns'])} {list(self.schema_info['json_columns'].keys())}")
        print(f"Boolean column tables detected: {len(self.schema_info['boolean_columns'])}")
        print("="*50)

        # Determine thread pool size
        total_tables = len(self.schema_info["migration_order"])
        pool_size = min(self.max_workers, total_tables)
        logger.info(f"Starting parallel migration using ThreadPoolExecutor with {pool_size} workers")

        total_rows = 0
        failed_tables = []
        table_statistics = []

        # Execute workers concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = {
                executor.submit(self._process_table, table_name): table_name
                for table_name in self.schema_info["migration_order"]
            }

            completed_count = 0
            for future in concurrent.futures.as_completed(futures):
                table_name = futures[future]
                completed_count += 1
                print(f"Completed {completed_count}/{total_tables} tables")
                
                try:
                    stats = future.result()
                    table_statistics.append(stats)
                    if stats["success"]:
                        total_rows += stats["rows"]
                    else:
                        failed_tables.append(table_name)
                except Exception as e:
                    logger.error(f"Worker thread for table {table_name} generated an unhandled exception: {e}")
                    failed_tables.append(table_name)
                    table_statistics.append({
                        "table": table_name,
                        "success": False,
                        "rows": 0,
                        "duration": 0.0,
                        "error": str(e)
                    })

        logger.info(
            f"Bulk load complete. "
            f"Total rows loaded: {total_rows} | "
            f"Failed tables: {len(failed_tables)}"
        )
        if failed_tables:
            logger.warning(f"Failed tables: {failed_tables}")

        # Post-process: Add foreign keys on a single connection
        main_conn = get_postgres_connection()
        try:
            print("\n--- Adding Foreign Key Constraints ---")
            fk_success, fk_failed = add_foreign_keys(main_conn, self.schema_info)
            print(f"FK constraints added: {fk_success}")
            print(f"FK constraints failed: {len(fk_failed)}")
        finally:
            main_conn.close()

        # Step 5: Validate
        print("\n--- Step 5: Validating migration ---")
        success = self._validate()
        
        # End pipeline timing
        pipeline_duration = time.perf_counter() - pipeline_start

        # Calculate performance metrics
        total_tables_count = len(table_statistics)
        success_tables_count = sum(1 for t in table_statistics if t["success"])
        failed_tables_count = total_tables_count - success_tables_count
        
        if total_tables_count > 0:
            avg_duration = sum(t["duration"] for t in table_statistics) / total_tables_count
            fastest_table = min(table_statistics, key=lambda x: x["duration"])
            slowest_table = max(table_statistics, key=lambda x: x["duration"])
        else:
            avg_duration = 0.0
            fastest_table = {"table": "N/A", "duration": 0.0}
            slowest_table = {"table": "N/A", "duration": 0.0}
            
        throughput = total_rows / pipeline_duration if pipeline_duration > 0 else 0.0

        # Performance Summary Display
        print("\n" + "="*48)
        print("PERFORMANCE SUMMARY")
        print("="*48 + "\n")
        print(f"Workers Used        : {pool_size}\n")
        print(f"Tables Migrated     : {success_tables_count}")
        print(f"Failed Tables       : {failed_tables_count}\n")
        print(f"Rows Migrated       : {total_rows:,}\n")
        print(f"Total Time          : {pipeline_duration:.2f} sec\n")
        print(f"Average/Table       : {avg_duration:.2f} sec\n")
        print(f"Throughput          : {int(throughput):,} rows/sec\n")
        print(f"Fastest Table       : {fastest_table['table']} ({fastest_table['duration']:.2f} sec)\n")
        print(f"Slowest Table       : {slowest_table['table']} ({slowest_table['duration']:.2f} sec)\n")
        print("="*48)

        # Slowest Tables Report
        sorted_stats = sorted(table_statistics, key=lambda x: x["duration"], reverse=True)
        print("\nTop 5 Slowest Tables\n")
        for i, stats in enumerate(sorted_stats[:5], 1):
            print(f"{i}. {stats['table']:<15} {stats['duration']:.2f} sec")

        # Final summary
        print("\n" + "="*50)
        print("PIPELINE COMPLETE")
        print(f"Total rows migrated : {total_rows}")
        print(f"Failed tables       : {len(failed_tables)}")
        print(f"Validation          : {'PASSED' if success else 'FAILED'}")
        print("="*50)
