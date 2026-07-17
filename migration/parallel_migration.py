import sys
import os
import logging
import time
import concurrent.futures
import threading
import json
import tempfile
from datetime import datetime

# Ensure the project root is in the Python search path.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from utils.schema_analyzer import analyze_schema
from migration.extract import extract_table_data, get_table_schema
from migration.transformer import transform_table
from migration.loader import load_table, add_foreign_keys, ConnectionHolder, RetryTracker, execute_with_retry
from validation.Validate import run_validation
from config.db_config import get_postgres_connection, init_pools, dispose_pools, get_mysql_engine
import config.db_config as db_cfg
from utils.logger import setup_logger
import config

logger = logging.getLogger("migration")

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

class CheckpointManager:
    _lock = threading.Lock()
    _file_existed = None

    @classmethod
    def load_checkpoint(cls, current_migration_order):
        """
        Loads and validates the checkpoint file.
        Returns a dictionary representing checkpoint data, or None if no valid checkpoint is found.
        """
        if getattr(config, "FORCE_FRESH_MIGRATION", False):
            logger.info("FORCE_FRESH_MIGRATION is enabled. Ignoring existing checkpoint.")
            return None

        if not getattr(config, "ENABLE_CHECKPOINT", True):
            return None

        checkpoint_path = config.CHECKPOINT_FILE
        if not os.path.exists(checkpoint_path):
            return None

        with cls._lock:
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if not isinstance(data, dict) or "completed_tables" not in data:
                    logger.warning("Checkpoint file has invalid structure. Starting a fresh migration.")
                    return None
                
                completed_tables = data["completed_tables"]
                unknown_tables = [t for t in completed_tables if t not in current_migration_order]
                if unknown_tables:
                    logger.warning(f"Checkpoint contains unknown tables not present in the current migration order: {unknown_tables}")
                    logger.warning("Checkpoint appears incompatible. Unknown tables will be ignored.")
                
                logger.info("Checkpoint Loaded")
                return data
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Corrupted or invalid checkpoint JSON file: {e}. Starting a fresh migration.")
                return None

    @classmethod
    def write_checkpoint(cls, migration_id, completed_tables):
        """
        Atomically writes checkpoint data and metadata to config.CHECKPOINT_FILE.
        Uses a temporary file and os.replace().
        """
        if not getattr(config, "ENABLE_CHECKPOINT", True):
            return

        with cls._lock:
            try:
                checkpoint_path = config.CHECKPOINT_FILE
                temp_dir = os.path.dirname(os.path.abspath(checkpoint_path))
                os.makedirs(temp_dir, exist_ok=True)
                
                if cls._file_existed is None:
                    cls._file_existed = os.path.exists(checkpoint_path)

                checkpoint_data = {
                    "migration_id": migration_id,
                    "creation_timestamp": datetime.now().isoformat(),
                    "completed_tables": completed_tables
                }

                with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as temp_f:
                    json.dump(checkpoint_data, temp_f, indent=4)
                    temp_f.flush()
                    os.fsync(temp_f.fileno())
                    temp_filepath = temp_f.name

                os.replace(temp_filepath, checkpoint_path)
                
                if not cls._file_existed:
                    logger.info("Checkpoint Created")
                    cls._file_existed = True
                else:
                    logger.info("Checkpoint Updated")
            except Exception as e:
                logger.error(f"Failed to write checkpoint atomically: {e}")

    @classmethod
    def remove_checkpoint(cls):
        """
        Safely removes the checkpoint file.
        """
        if not getattr(config, "ENABLE_CHECKPOINT", True):
            return

        with cls._lock:
            checkpoint_path = config.CHECKPOINT_FILE
            if os.path.exists(checkpoint_path):
                try:
                    os.remove(checkpoint_path)
                    logger.info("Checkpoint Removed")
                    cls._file_existed = False
                except Exception as e:
                    logger.error(f"Failed to remove checkpoint file: {e}")

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

    def _extract(self, table_name, engine=None):
        """
        Extract data from MySQL for a single table.
        """
        return extract_table_data(table_name, engine=engine)

    def _transform(self, df, table_name):
        """
        Transform MySQL data to PostgreSQL-compatible formats for a single table.
        """
        return transform_table(df, table_name, self.schema_info)

    def _load(self, pg_conn, table_name, df, schema, is_first_chunk=True, is_last_chunk=True, chunk_number=1):
        """
        Load transformed data to PostgreSQL for a single table.
        """
        return load_table(pg_conn, table_name, df, schema, self.schema_info, is_first_chunk, is_last_chunk, chunk_number)

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
        worker_id = WorkerIdMapper.get_worker_id()
        
        start_time = time.perf_counter()
        pg_conn = None
        fk_disabled = False
        try:
            logger.info(f"[{worker_id}] [{table_name}] Started")
            
            # 1. Create connection and wrap it in a ConnectionHolder (uses pool if enabled)
            pg_conn = get_postgres_connection()
            conn_holder = ConnectionHolder(pg_conn)
            
            # 2. Disable FK enforcement on this connection/session
            cursor = conn_holder.conn.cursor()
            cursor.execute("SET session_replication_role = replica;")
            conn_holder.conn.commit()
            cursor.close()
            fk_disabled = True
            logger.info(f"[{worker_id}] [{table_name}] FK constraints disabled for bulk load")

            # Get the shared MySQL engine (uses pool engine if enabled)
            mysql_engine = get_mysql_engine()

            # 3. Coordinate stages (using generators for chunking)
            chunks_generator = self._extract(table_name, engine=mysql_engine)
            schema = get_table_schema(table_name)
            
            total_rows_loaded = 0
            chunk_count = 0
            chunk_sizes = []

            try:
                first_chunk = next(chunks_generator)
                chunk_count += 1
                chunk_sizes.append(len(first_chunk))
            except StopIteration:
                logger.info(f"[{worker_id}] [{table_name}] Table is empty, creating structure only")
                self._load(conn_holder, table_name, None, schema, is_first_chunk=True, is_last_chunk=True, chunk_number=0)
                
                cursor = conn_holder.conn.cursor()
                cursor.execute("SET session_replication_role = DEFAULT;")
                conn_holder.conn.commit()
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
                try:
                    next_chunk = next(chunks_generator)
                    is_last = False
                except StopIteration:
                    is_last = True

                is_first = (chunk_count == 1)
                
                logger.info(f"[{worker_id}] [{table_name}] Extract Complete")
                transformed_chunk = self._transform(current_chunk, table_name)
                logger.info(f"[{worker_id}] [{table_name}] Transform Complete")
                
                rows = self._load(conn_holder, table_name, transformed_chunk, schema, 
                                  is_first_chunk=is_first, is_last_chunk=is_last, chunk_number=chunk_count)
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
            cursor = conn_holder.conn.cursor()
            cursor.execute("SET session_replication_role = DEFAULT;")
            conn_holder.conn.commit()
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
            if 'conn_holder' in locals() and conn_holder.conn:
                if fk_disabled:
                    try:
                        cursor = conn_holder.conn.cursor()
                        cursor.execute("SET session_replication_role = DEFAULT;")
                        conn_holder.conn.commit()
                        cursor.close()
                        logger.info(f"[{worker_id}] [{table_name}] FK constraints re-enabled in finally block")
                    except Exception as ex:
                        logger.error(f"[{worker_id}] [{table_name}] Failed to restore FK constraints in finally block: {ex}")
                # Returns connection back to the pool
                conn_holder.conn.close()

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

        # Initialize connection pools exactly once
        init_pools(self.max_workers)

        try:
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

            # Load Checkpoint and Filter completed tables
            checkpoint_data = CheckpointManager.load_checkpoint(self.schema_info["migration_order"])
            completed_tables_tracker = {}
            
            if checkpoint_data:
                completed_tables_tracker = checkpoint_data.get("completed_tables", {})
                skipped_tables = [t for t in self.schema_info["migration_order"] if completed_tables_tracker.get(t) == "completed"]
                remaining_tables = [t for t in self.schema_info["migration_order"] if completed_tables_tracker.get(t) != "completed"]
                
                logger.info(f"Skipped Tables: {len(skipped_tables)} {skipped_tables}")
                logger.info(f"Remaining Tables: {len(remaining_tables)} {remaining_tables}")
                if skipped_tables:
                    logger.info("Migration Resumed")
            else:
                skipped_tables = []
                remaining_tables = list(self.schema_info["migration_order"])

            # Determine thread pool size
            total_tables = len(remaining_tables)
            pool_size = min(self.max_workers, max(1, total_tables))
            logger.info(f"Worker Pool Created with {pool_size} workers")

            total_rows = 0
            failed_tables = []
            table_statistics = []

            if total_tables > 0:
                with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
                    futures = {
                        executor.submit(self._process_table, table_name): table_name
                        for table_name in remaining_tables
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
                                completed_tables_tracker[table_name] = "completed"
                                CheckpointManager.write_checkpoint(migration_id, completed_tables_tracker)
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

            # Post-process: Add foreign keys on a single connection wrapped with retry helper
            main_conn = get_postgres_connection()
            try:
                logger.info("Foreign Keys Started")
                print("\n--- Adding Foreign Key Constraints ---")
                fk_success, fk_failed = execute_with_retry(add_foreign_keys, "ADD FOREIGN KEY", main_conn, self.schema_info)
                print(f"FK constraints added: {fk_success}")
                print(f"FK constraints failed: {len(fk_failed)}")
                logger.info("Foreign Keys Complete")
            finally:
                try:
                    main_conn.close()
                except Exception:
                    pass

            # Step 5: Validate
            success = True
            if config.ENABLE_VALIDATION:
                logger.info("Validation Started")
                print("\n--- Step 5: Validating migration ---")
                success = self._validate()
                logger.info("Validation Complete")
            
            pipeline_duration = time.perf_counter() - pipeline_start

            total_tables_count = len(table_statistics)
            success_tables_count = sum(1 for t in table_statistics if t["success"])
            failed_tables_count = total_tables_count - success_tables_count
            
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

            total_chunks = sum(t.get("chunks_processed", 0) for t in table_statistics)
            largest_chunk = max((t.get("largest_chunk_size", 0) for t in table_statistics), default=0)
            avg_chunk_size = total_rows / total_chunks if total_chunks > 0 else 0.0

            strategy_str = "COPY" if config.USE_POSTGRES_COPY else "execute_values"

            # Connection Pool reporting stats
            pool_enabled_str = "Yes" if config.USE_CONNECTION_POOL else "No"
            pool_size_str = str(config.POOL_SIZE) if config.USE_CONNECTION_POOL else "N/A"
            reused_conn_count = (db_cfg.postgres_pool.reused_count + db_cfg.mysql_pool.reused_count) if (config.USE_CONNECTION_POOL and db_cfg.postgres_pool and db_cfg.mysql_pool) else 0
            recreated_conn_count = (db_cfg.postgres_pool.recreated_count + db_cfg.mysql_pool.recreated_count) if (config.USE_CONNECTION_POOL and db_cfg.postgres_pool and db_cfg.mysql_pool) else 0

            if config.ENABLE_PERFORMANCE_REPORT:
                print("\n" + "="*48)
                print("PERFORMANCE SUMMARY")
                print("="*48 + "\n")
                print(f"Workers Used        : {pool_size}\n")
                print(f"Loading Strategy    : {strategy_str}\n")
                
                # Connection pooling metrics
                print(f"Connection Pool Enabled : {pool_enabled_str}")
                print(f"Pool Size               : {pool_size_str}")
                print(f"Connections Reused      : {reused_conn_count}")
                print(f"Connections Recreated   : {recreated_conn_count}\n")

                print(f"Tables Resumed      : {'Yes' if len(skipped_tables) > 0 else 'No'}")
                print(f"Tables Skipped      : {len(skipped_tables)}")
                print(f"Tables Executed     : {len(remaining_tables)}\n")

                print(f"Tables Migrated     : {success_tables_count}")
                print(f"Failed Tables       : {failed_tables_count}\n")
                
                print(f"Retry Count         : {RetryTracker.retry_count}")
                print(f"Recovered Failures  : {RetryTracker.recovered_failures}")
                print(f"Permanent Failures  : {RetryTracker.permanent_failures}\n")
                
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

                logger.info("================================================")
                logger.info("PERFORMANCE SUMMARY")
                logger.info("================================================")
                logger.info(f"Workers             : {pool_size}")
                logger.info(f"Loading Strategy    : {strategy_str}")
                logger.info(f"Connection Pool Enabled : {pool_enabled_str}")
                logger.info(f"Pool Size               : {pool_size_str}")
                logger.info(f"Connections Reused      : {reused_conn_count}")
                logger.info(f"Connections Recreated   : {recreated_conn_count}")
                logger.info(f"Tables Resumed      : {'Yes' if len(skipped_tables) > 0 else 'No'}")
                logger.info(f"Tables Skipped      : {len(skipped_tables)}")
                logger.info(f"Tables Executed     : {len(remaining_tables)}")
                logger.info(f"Tables Migrated     : {success_tables_count}")
                logger.info(f"Failed Tables       : {failed_tables_count}")
                logger.info(f"Retry Count         : {RetryTracker.retry_count}")
                logger.info(f"Recovered Failures  : {RetryTracker.recovered_failures}")
                logger.info(f"Permanent Failures  : {RetryTracker.permanent_failures}")
                logger.info(f"Rows Migrated       : {total_rows}")
                logger.info(f"Pipeline Duration   : {pipeline_duration:.2f} sec")
                logger.info(f"Throughput          : {throughput:,.2f} rows/sec")
                logger.info(f"Fastest Table       : {fastest_table['table']} ({fastest_table['duration']:.2f} sec)")
                logger.info(f"Slowest Table       : {slowest_table['table']} ({slowest_table['duration']:.2f} sec)")
                logger.info(f"Chunks Processed    : {total_chunks}")
                logger.info(f"Largest Chunk Size  : {largest_chunk}")
                logger.info(f"Average Chunk Size  : {avg_chunk_size:.2f}")
                logger.info("================================================")

                sorted_stats = sorted(successful_stats, key=lambda x: x["duration"], reverse=True)
                print(f"\nTop {config.TOP_SLOW_TABLE_COUNT} Slowest Tables\n")
                for i, stats in enumerate(sorted_stats[:config.TOP_SLOW_TABLE_COUNT], 1):
                    print(f"{i}. {stats['table']:<15} {stats['duration']:.2f} sec")

                logger.info(f"Top {config.TOP_SLOW_TABLE_COUNT} Slowest Tables:")
                for i, stats in enumerate(sorted_stats[:config.TOP_SLOW_TABLE_COUNT], 1):
                    logger.info(f"  {i}. {stats['table']} ({stats['duration']:.2f} sec)")

            if len(failed_tables) == 0 and (not config.ENABLE_VALIDATION or success):
                CheckpointManager.remove_checkpoint()

            logger.info("================================================")
            logger.info("FINAL SUMMARY")
            logger.info("================================================")
            logger.info(f"Migration Status    : {'SUCCESS' if len(failed_tables) == 0 else 'FAILED'}")
            logger.info(f"Migration ID        : {migration_id}")
            logger.info(f"Successful Tables   : {success_tables_count}")
            logger.info(f"Failed Tables       : {len(failed_tables)}")
            logger.info(f"Rows Migrated       : {total_rows}")
            logger.info(f"Duration            : {pipeline_duration:.2f} sec")
            logger.info(f"Validation Result   : {'PASSED' if (not config.ENABLE_VALIDATION or success) else 'FAILED'}")
            logger.info("================================================")

            logger.info("Migration Finished")

            print("\n" + "="*50)
            print("PIPELINE COMPLETE")
            print(f"Total rows migrated : {total_rows}")
            print(f"Failed tables       : {len(failed_tables)}")
            print(f"Validation          : {'PASSED' if (not config.ENABLE_VALIDATION or success) else 'FAILED'}")
            print("="*50)

        finally:
            # Dispose of both connection pools exactly once during application shutdown
            dispose_pools()
