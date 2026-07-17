import sys
import os
import logging
import time
import concurrent.futures
import threading
from datetime import datetime

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
from utils.logger import setup_logger
import config

class WorkerIdMapper:
    _lock = threading.Lock()
    _mapping = {}
    _counter = 1

    @classmethod
    def get_worker_id(cls):
        ident = threading.get_ident()
        with cls._lock:
            if ident not in cls._mapping:
                if threading.current_thread() is threading.main_thread():
                    cls._mapping[ident] = "Main"
                else:
                    cls._mapping[ident] = f"Worker-{cls._counter}"
                    cls._counter += 1
            return cls._mapping[ident]

class ParallelMigrationManager:
    def __init__(self, max_workers=None):
        """
        Initialize the ParallelMigrationManager.
        
        :param max_workers: The maximum number of threads in the ThreadPoolExecutor.
                            If None, falls back to config.MAX_WORKERS.
        """
        self.schema_info = None
        self.max_workers = max_workers if max_workers is not None else config.MAX_WORKERS

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

    def _load(self, pg_conn, table_name, df, schema, is_first_chunk=True, is_last_chunk=True):
        """
        Load transformed data to PostgreSQL for a single table.
        """
        return load_table(pg_conn, table_name, df, schema, self.schema_info, is_first_chunk, is_last_chunk)

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
        logger = logging.getLogger("migration")
        worker_id = WorkerIdMapper.get_worker_id()
        
        start_time = time.perf_counter()
        pg_conn = None
        fk_disabled = False
        try:
            logger.info(f"[{worker_id}] [{table_name}] Started")
            
            # 1. Create connection
            pg_conn = get_postgres_connection()
            
            # 2. Disable FK enforcement on this connection/session
            cursor = pg_conn.cursor()
            cursor.execute("SET session_replication_role = replica;")
            pg_conn.commit()
            cursor.close()
            fk_disabled = True
            logger.info(f"[{worker_id}] [{table_name}] FK constraints disabled for bulk load")

            # 3. Coordinate stages (using generators for chunking)
            chunks_generator = self._extract(table_name)
            schema = get_table_schema(table_name)
            
            total_rows_loaded = 0
            chunk_count = 0
            chunk_sizes = []

            # Try to get the first chunk
            try:
                first_chunk = next(chunks_generator)
                chunk_count += 1
                chunk_sizes.append(len(first_chunk))
            except StopIteration:
                # Table is empty, create schema structure only without DataFrame inserts
                logger.info(f"[{worker_id}] [{table_name}] Table is empty, creating structure only")
                self._load(pg_conn, table_name, None, schema, is_first_chunk=True, is_last_chunk=True)
                
                # Restore FK and exit
                cursor = pg_conn.cursor()
                cursor.execute("SET session_replication_role = DEFAULT;")
                pg_conn.commit()
                cursor.close()
                fk_disabled = False
                
                duration = time.perf_counter() - start_time
                logger.info(f"[{worker_id}] [{table_name}] Completed Successfully")
                logger.info(f"[{worker_id}] [{table_name}] Duration: {duration:.2f} sec")
                
                return {
                    "table": table_name,
                    "success": True,
                    "rows": 0,
                    "duration": duration,
                    "chunks_processed": 0,
                    "largest_chunk_size": 0,
                    "average_chunk_size": 0.0
                }

            current_chunk = first_chunk
            while True:
                # Peek at the next chunk to determine if current_chunk is the last one
                try:
                    next_chunk = next(chunks_generator)
                    is_last = False
                except StopIteration:
                    is_last = True

                is_first = (chunk_count == 1)
                
                logger.info(f"[{worker_id}] [{table_name}] Extract Complete")
                transformed_chunk = self._transform(current_chunk, table_name)
                logger.info(f"[{worker_id}] [{table_name}] Transform Complete")
                
                rows = self._load(pg_conn, table_name, transformed_chunk, schema, 
                                  is_first_chunk=is_first, is_last_chunk=is_last)
                total_rows_loaded += rows
                logger.info(f"[{worker_id}] [{table_name}] Load Complete")
                logger.info(f"[{worker_id}] [{table_name}] Rows Loaded: {rows}")
                logger.info(f"[{worker_id}] [{table_name}] Chunk {chunk_count} | {rows} rows loaded")

                if is_last:
                    break

                current_chunk = next_chunk
                chunk_count += 1
                chunk_sizes.append(len(next_chunk))

            # 4. Restore FK enforcement on this connection/session
            cursor = pg_conn.cursor()
            cursor.execute("SET session_replication_role = DEFAULT;")
            pg_conn.commit()
            cursor.close()
            fk_disabled = False
            logger.info(f"[{worker_id}] [{table_name}] FK constraints re-enabled")

            duration = time.perf_counter() - start_time
            logger.info(f"[{worker_id}] [{table_name}] Completed Successfully")
            logger.info(f"[{worker_id}] [{table_name}] Duration: {duration:.2f} sec")
            
            largest_chunk = max(chunk_sizes) if chunk_sizes else 0
            avg_chunk = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0.0

            return {
                "table": table_name,
                "success": True,
                "rows": total_rows_loaded,
                "duration": duration,
                "chunks_processed": chunk_count,
                "largest_chunk_size": largest_chunk,
                "average_chunk_size": avg_chunk
            }
        except Exception as e:
            duration = time.perf_counter() - start_time
            exc_type = type(e).__name__
            exc_msg = str(e)
            
            log_msg = f"[{worker_id}] [{table_name}] Failed: Exception Type: {exc_type}, Message: {exc_msg}"
            
            if config.DEBUG:
                logger.error(log_msg, exc_info=True)
            else:
                logger.error(log_msg)
                
            return {
                "table": table_name,
                "success": False,
                "rows": 0,
                "duration": duration,
                "error": str(e),
                "chunks_processed": 0,
                "largest_chunk_size": 0,
                "average_chunk_size": 0.0
            }
        finally:
            if pg_conn:
                if fk_disabled:
                    try:
                        cursor = pg_conn.cursor()
                        cursor.execute("SET session_replication_role = DEFAULT;")
                        pg_conn.commit()
                        cursor.close()
                        logger.info(f"[{worker_id}] [{table_name}] FK constraints re-enabled in finally block")
                    except Exception as ex:
                        logger.error(f"[{worker_id}] [{table_name}] Failed to restore FK constraints in finally block: {ex}")
                pg_conn.close()

    def run(self):
        """
        Run the complete migration pipeline in parallel using a ThreadPoolExecutor.
        """
        pipeline_start = time.perf_counter()

        # Generate Migration ID
        migration_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize structured logger
        logger = setup_logger(migration_id)
        
        logger.info(f"Migration ID: {migration_id}")
        logger.info("Migration Started")
        
        logger.info("Configuration Loaded")
        logger.info("================================================")
        logger.info("Configuration")
        logger.info("================================================")
        logger.info(f"Workers : {self.max_workers}")
        logger.info(f"Validation : {'Enabled' if config.ENABLE_VALIDATION else 'Disabled'}")
        logger.info(f"Performance Report : {'Enabled' if config.ENABLE_PERFORMANCE_REPORT else 'Disabled'}")
        logger.info(f"Progress Report : {'Enabled' if config.ENABLE_PROGRESS_REPORT else 'Disabled'}")
        logger.info(f"Slow Table Count : {config.TOP_SLOW_TABLE_COUNT}")
        logger.info(f"Log Level : {config.LOG_LEVEL}")
        logger.info("================================================")

        # Print high-level banner to console
        print("\n" + "="*50)
        print(config.APP_NAME.upper())
        print("="*50)

        # 1. Analyze Schema (Runs EXACTLY once)
        logger.info("Schema Analysis Started")
        self.schema_info = self._analyze_schema()
        logger.info("Schema Analysis Complete")

        # Centralize schema_info reference in helpers to avoid redundant calls
        import migration.extract as ext
        import migration.transformer as trans
        import migration.loader as load
        ext.schema_info = self.schema_info
        trans.schema_info = self.schema_info
        load.schema_info = self.schema_info

        # Print summary of what was auto-detected on console
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
        logger.info(f"Worker Pool Created with {pool_size} workers")

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
                if config.ENABLE_PROGRESS_REPORT:
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
                        "error": str(e),
                        "chunks_processed": 0,
                        "largest_chunk_size": 0,
                        "average_chunk_size": 0.0
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
            logger.info("Foreign Keys Started")
            print("\n--- Adding Foreign Key Constraints ---")
            fk_success, fk_failed = add_foreign_keys(main_conn, self.schema_info)
            print(f"FK constraints added: {fk_success}")
            print(f"FK constraints failed: {len(fk_failed)}")
            logger.info("Foreign Keys Complete")
        finally:
            main_conn.close()

        # Step 5: Validate
        success = True
        if config.ENABLE_VALIDATION:
            logger.info("Validation Started")
            print("\n--- Step 5: Validating migration ---")
            success = self._validate()
            logger.info("Validation Complete")
        
        # End pipeline timing
        pipeline_duration = time.perf_counter() - pipeline_start

        # Calculate performance metrics
        total_tables_count = len(table_statistics)
        success_tables_count = sum(1 for t in table_statistics if t["success"])
        failed_tables_count = total_tables_count - success_tables_count
        
        # Filter stats to only successful migrations for fastest/slowest reporting
        successful_stats = [t for t in table_statistics if t["success"]]
        if successful_stats:
            avg_duration = sum(t["duration"] for t in successful_stats) / len(successful_stats)
            fastest_table = min(successful_stats, key=lambda x: x["duration"])
            slowest_table = max(successful_stats, key=lambda x: x["duration"])
        else:
            avg_duration = 0.0
            fastest_table = {"table": "N/A", "duration": 0.0}
            slowest_table = {"table": "N/A", "duration": 0.0}
            
        throughput = total_rows / pipeline_duration if pipeline_duration > 0 else 0.0

        # Chunk statistics
        total_chunks = sum(t.get("chunks_processed", 0) for t in table_statistics)
        largest_chunk = max((t.get("largest_chunk_size", 0) for t in table_statistics), default=0)
        avg_chunk_size = total_rows / total_chunks if total_chunks > 0 else 0.0

        if config.ENABLE_PERFORMANCE_REPORT:
            # Print performance summary to console
            print("\n" + "="*48)
            print("PERFORMANCE SUMMARY")
            print("="*48 + "\n")
            print(f"Workers Used        : {pool_size}\n")
            print(f"Tables Migrated     : {success_tables_count}")
            print(f"Failed Tables       : {failed_tables_count}\n")
            print(f"Rows Migrated       : {total_rows:,}\n")
            print(f"Total Time          : {pipeline_duration:.2f} sec\n")
            print(f"Average/Table       : {avg_duration:.2f} sec\n")
            print(f"Throughput          : {throughput:,.2f} rows/sec\n")
            print(f"Fastest Table       : {fastest_table['table']} ({fastest_table['duration']:.2f} sec)\n")
            print(f"Slowest Table       : {slowest_table['table']} ({slowest_table['duration']:.2f} sec)\n")
            print(f"Chunks Processed    : {total_chunks}")
            print(f"Largest Chunk Size  : {largest_chunk:,}")
            print(f"Average Chunk Size  : {avg_chunk_size:.2f}\n")
            print("="*48)

            # Log performance summary to log file
            logger.info("================================================")
            logger.info("PERFORMANCE SUMMARY")
            logger.info("================================================")
            logger.info(f"Workers             : {pool_size}")
            logger.info(f"Rows Migrated       : {total_rows}")
            logger.info(f"Pipeline Duration   : {pipeline_duration:.2f} sec")
            logger.info(f"Throughput          : {throughput:,.2f} rows/sec")
            logger.info(f"Fastest Table       : {fastest_table['table']} ({fastest_table['duration']:.2f} sec)")
            logger.info(f"Slowest Table       : {slowest_table['table']} ({slowest_table['duration']:.2f} sec)")
            logger.info(f"Chunks Processed    : {total_chunks}")
            logger.info(f"Largest Chunk Size  : {largest_chunk}")
            logger.info(f"Average Chunk Size  : {avg_chunk_size:.2f}")
            logger.info("================================================")

            # Slowest Tables Report
            sorted_stats = sorted(successful_stats, key=lambda x: x["duration"], reverse=True)
            print(f"\nTop {config.TOP_SLOW_TABLE_COUNT} Slowest Tables\n")
            for i, stats in enumerate(sorted_stats[:config.TOP_SLOW_TABLE_COUNT], 1):
                print(f"{i}. {stats['table']:<15} {stats['duration']:.2f} sec")

            # Log Slowest Tables to log file
            logger.info(f"Top {config.TOP_SLOW_TABLE_COUNT} Slowest Tables:")
            for i, stats in enumerate(sorted_stats[:config.TOP_SLOW_TABLE_COUNT], 1):
                logger.info(f"  {i}. {stats['table']} ({stats['duration']:.2f} sec)")

        # Log Final Summary to log file
        logger.info("================================================")
        logger.info("FINAL SUMMARY")
        logger.info("================================================")
        logger.info(f"Migration Status    : {'SUCCESS' if failed_tables_count == 0 else 'FAILED'}")
        logger.info(f"Migration ID        : {migration_id}")
        logger.info(f"Successful Tables   : {success_tables_count}")
        logger.info(f"Failed Tables       : {failed_tables_count}")
        logger.info(f"Rows Migrated       : {total_rows}")
        logger.info(f"Duration            : {pipeline_duration:.2f} sec")
        logger.info(f"Validation Result   : {'PASSED' if (not config.ENABLE_VALIDATION or success) else 'FAILED'}")
        logger.info("================================================")

        logger.info("Migration Finished")

        # Print Final summary to console (must continue to work exactly as before)
        print("\n" + "="*50)
        print("PIPELINE COMPLETE")
        print(f"Total rows migrated : {total_rows}")
        print(f"Failed tables       : {len(failed_tables)}")
        print(f"Validation          : {'PASSED' if (not config.ENABLE_VALIDATION or success) else 'FAILED'}")
        print("="*50)
