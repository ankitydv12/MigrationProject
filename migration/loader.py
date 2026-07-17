import psycopg2
import sys
import os
import logging
from sqlalchemy import inspect
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
import json
import io
import time
import threading

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from config.db_config import get_postgres_connection, get_mysql_engine
from utils.schema_analyzer import analyze_schema

logger = logging.getLogger(__name__)

# Schema metadata is lazy-loaded or injected by ParallelMigrationManager
schema_info = None

def _init_schema_info():
    """
    Lazy-load schema information if it hasn't been set yet.
    """
    global schema_info
    if schema_info is None:
        schema_info = analyze_schema()

from sqlalchemy.dialects.mysql import (
    INTEGER, BIGINT, SMALLINT, TINYINT,
    VARCHAR, TEXT, LONGTEXT,
    DATETIME, DATE,
    DECIMAL, FLOAT, JSON
)

class RetryTracker:
    _lock = threading.Lock()
    retry_count = 0
    recovered_failures = 0
    permanent_failures = 0

    @classmethod
    def record_retry(cls):
        with cls._lock:
            cls.retry_count += 1

    @classmethod
    def record_recovery(cls):
        with cls._lock:
            cls.recovered_failures += 1

    @classmethod
    def record_permanent_failure(cls):
        with cls._lock:
            cls.permanent_failures += 1

class ConnectionHolder:
    def __init__(self, conn):
        self.conn = conn

def recreate_connection(conn_holder):
    """
    Safely closes the old connection and creates a new one,
    disabling FK checks on the new connection/session.
    """
    try:
        conn_holder.conn.close()
    except Exception:
        pass
    new_conn = get_postgres_connection()
    cursor = new_conn.cursor()
    cursor.execute("SET session_replication_role = replica;")
    new_conn.commit()
    cursor.close()
    conn_holder.conn = new_conn

def execute_with_retry(operation, op_name, pg_conn_or_holder, *args, **kwargs):
    """
    Executes an operation with retry logic for transient database failures.
    Automatically handles connection recreation if pg_conn_or_holder is a ConnectionHolder.
    """
    import config
    
    enable_retry = getattr(config, "ENABLE_RETRY", True)
    max_attempts = getattr(config, "MAX_RETRY_ATTEMPTS", 3)
    initial_delay = getattr(config, "RETRY_INITIAL_DELAY", 1)
    backoff_factor = getattr(config, "RETRY_BACKOFF_FACTOR", 2)
    
    if not enable_retry:
        conn = pg_conn_or_holder.conn if isinstance(pg_conn_or_holder, ConnectionHolder) else pg_conn_or_holder
        return operation(conn, *args, **kwargs)
        
    transient_errors = (
        psycopg2.OperationalError,
        psycopg2.InterfaceError,
        ConnectionError,
        TimeoutError
    )
    
    delay = initial_delay
    conn_holder = pg_conn_or_holder if isinstance(pg_conn_or_holder, ConnectionHolder) else ConnectionHolder(pg_conn_or_holder)
    
    for attempt in range(1, max_attempts + 1):
        try:
            result = operation(conn_holder.conn, *args, **kwargs)
            if attempt > 1:
                RetryTracker.record_recovery()
                logger.info(f"[{op_name}] Final Success on attempt {attempt}/{max_attempts}")
            return result
        except transient_errors as e:
            if attempt == max_attempts:
                RetryTracker.record_permanent_failure()
                logger.error(f"[{op_name}] Final Failure on attempt {attempt}/{max_attempts}: {e}")
                raise
                
            RetryTracker.record_retry()
            logger.warning(f"[{op_name}] Failed")
            logger.warning(f"[{op_name}] Retry {attempt}/{max_attempts}")
            logger.warning(f"[{op_name}] Waiting {delay} sec")
            
            recreate_connection(conn_holder)
            time.sleep(delay)
            delay *= backoff_factor

def map_mysql_type_to_postgres(mysql_type, table_name, col_name):
    """
    Converts SQLAlchemy MySQL type object to PostgreSQL 
    type string.
    
    mysql_type comes from inspector.get_columns()
    which returns SQLAlchemy type objects.
    """
    _init_schema_info()
    
    # convert type object to string for easy comparison
    type_str = str(mysql_type).upper()
    
    # JSON columns - check table mapping
    if "JSON" in type_str:
        return "JSONB"
    
    # UUID columns - VARCHAR(36) in UUID tables
    if "VARCHAR(36)" in type_str and table_name in schema_info["uuid_tables"]:
        return "UUID"
    
    # Boolean - TINYINT(1) or if listed in boolean_columns
    if "TINYINT(1)" in type_str or "BOOL" in type_str or col_name in schema_info["boolean_columns"].get(table_name, []):
        return "BOOLEAN"
    
    # Integer types
    if "BIGINT" in type_str:
        return "BIGINT"
    if "SMALLINT" in type_str:
        return "SMALLINT"
    if "TINYINT" in type_str:
        return "SMALLINT"
    if "INT" in type_str:
        return "INTEGER"
    
    # String types
    if "VARCHAR" in type_str:
        return type_str.replace("VARCHAR", "VARCHAR")
    if "LONGTEXT" in type_str:
        return "TEXT"
    if "TEXT" in type_str:
        return "TEXT"
    
    # Date types
    if "DATETIME" in type_str or "TIMESTAMP" in type_str:
        return "TIMESTAMP"
    if "DATE" in type_str:
        return "DATE"
    
    # Numeric types
    if "DECIMAL" in type_str or "NUMERIC" in type_str:
        return type_str.replace("DECIMAL", "NUMERIC")
    if "FLOAT" in type_str:
        return "DOUBLE PRECISION"
    if "DOUBLE" in type_str:
        return "DOUBLE PRECISION"
    
    # Default fallback
    return "VARCHAR(255)"


def create_postgres_table(pg_conn, table_name, mysql_schema):
    """
    Creates table in PostgreSQL with correct types.
    Drops table first if it exists.
    """
    cursor = pg_conn.cursor()
    
    try:
        # Step 1: drop table if exists (clean start)
        cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
        pg_conn.commit()
        
        # Step 2: map columns to Postgres types
        col_definitions = []
        for col in mysql_schema["columns"]:
            col_name = col["name"]
            mysql_type = col["type"]
            
            # map type
            pg_type = map_mysql_type_to_postgres(
                mysql_type, 
                table_name, 
                col_name
            )
            
            # handle NULL/NOT NULL constraint
            nullable_str = "" if col["nullable"] else " NOT NULL"
            
            # handle primary key (simple id columns)
            pk_str = ""
            if col_name == "id":
                pk_str = " PRIMARY KEY"
                
            col_definitions.append(
                f"{col_name} {pg_type}{nullable_str}{pk_str}"
            )
            
        # Step 3: build CREATE TABLE SQL
        cols_sql = ",\n    ".join(col_definitions)
        create_sql = f"""
            CREATE TABLE {table_name} (
                {cols_sql}
            );
        """
        
        # Step 4: execute CREATE TABLE
        cursor.execute(create_sql)
        pg_conn.commit()
        logger.info(f"Created table in PostgreSQL: {table_name}")
        
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"Failed to create table {table_name}: {e}")
        raise
        
    finally:
        cursor.close()


def prepare_copy_buffer(df):
    """
    Converts DataFrame to an in-memory CSV buffer (io.StringIO)
    optimized for PostgreSQL COPY. Uses UTF-8 and Unix line endings.
    """
    # Create a shallow copy of column references (underlying data arrays are not copied)
    shallow_df = df.copy(deep=False)
    
    for col in shallow_df.columns:
        # Handle Boolean columns
        if shallow_df[col].dtype == 'bool' or shallow_df[col].dtype == 'boolean':
            shallow_df[col] = shallow_df[col].apply(
                lambda val: None if (val is None or pd.isna(val)) else ('true' if val else 'false')
            ).astype(object)
        # Handle Object/Datetime/Timestamp/JSON dict columns
        elif (shallow_df[col].dtype == 'object' or 
              isinstance(shallow_df[col].dtype, pd.DatetimeTZDtype) or 
              shallow_df[col].dtype == 'datetime64[ns]'):
            
            def format_val(val):
                if val is None or pd.isna(val) or val is pd.NaT:
                    return None
                if isinstance(val, dict):
                    return json.dumps(val)
                if isinstance(val, bool):
                    return 'true' if val else 'false'
                if isinstance(val, pd.Timestamp):
                    return val.isoformat()
                return val

            shallow_df[col] = shallow_df[col].apply(format_val)
            
    csv_buffer = io.StringIO()
    # Explicitly use lineterminator="\n" for Unix line endings and standard CSV settings
    shallow_df.to_csv(csv_buffer, index=False, header=False, na_rep='\\N', sep=',', quotechar='"', doublequote=True, lineterminator="\n")
    csv_buffer.seek(0)
    return csv_buffer


def insert_table_data(conn_holder, table_name, df, chunk_number=1):
    """
    Inserts DataFrame into PostgreSQL table.
    Uses COPY FROM STDIN or falls back to execute_values based on config.
    """
    if df is None or df.empty:
        logger.warning(f"Empty/None DataFrame for {table_name}, skipping insert")
        return 0
    
    import config
    use_copy = getattr(config, "USE_POSTGRES_COPY", True)
    
    if use_copy:
        csv_buffer = prepare_copy_buffer(df)
        columns_str = ", ".join(f'"{col}"' for col in df.columns)
        copy_sql = f'COPY "{table_name}" ({columns_str}) FROM STDIN WITH CSV NULL \'\\N\''
        
        def run_copy(conn):
            logger.info(f"[{table_name}] COPY Started | Chunk: {chunk_number}")
            cursor = conn.cursor()
            try:
                start_time = time.perf_counter()
                cursor.copy_expert(copy_sql, csv_buffer)
                duration = time.perf_counter() - start_time
                conn.commit()
                rows_sec = len(df) / duration if duration > 0 else 0.0
                logger.info(f"[{table_name}] COPY Completed | Chunk: {chunk_number} | Rows Loaded: {len(df)} | Duration: {duration:.4f} sec | Throughput: {rows_sec:.2f} rows/sec")
            finally:
                cursor.close()
            return len(df)
            
        return execute_with_retry(run_copy, f"{table_name} COPY", conn_holder)
    else:
        records = prepare_records(df, table_name)
        columns_str = ", ".join(f'"{col}"' for col in df.columns)
        insert_sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES %s'
        
        def run_insert(conn):
            logger.info(f"[{table_name}] INSERT Started (execute_values) | Chunk: {chunk_number}")
            cursor = conn.cursor()
            try:
                start_time = time.perf_counter()
                execute_values(cursor, insert_sql, records, page_size=1000)
                duration = time.perf_counter() - start_time
                conn.commit()
                rows_sec = len(records) / duration if duration > 0 else 0.0
                logger.info(f"[{table_name}] INSERT Completed (execute_values) | Chunk: {chunk_number} | Rows Loaded: {len(records)} | Duration: {duration:.4f} sec | Throughput: {rows_sec:.2f} rows/sec")
            finally:
                cursor.close()
            return len(records)
            
        return execute_with_retry(run_insert, f"{table_name} INSERT", conn_holder)

def prepare_records(df, table_name):
    """
    Converts DataFrame to list of tuples for psycopg2.
    Handles JSON, UUID, boolean, NaN values.
    """
    records = []
    
    for _, row in df.iterrows():
        record = []
        for col in df.columns:
            value = row[col]
            
            # handle NaN/NaT → None
            if (isinstance(value, float) and np.isnan(value)) or value is pd.NaT:
                record.append(None)
            
            # handle pandas Timestamp → Python datetime
            elif isinstance(value, pd.Timestamp):
                record.append(value.to_pydatetime())
            
            # handle dict → JSON string for JSONB
            elif isinstance(value, dict):
                record.append(json.dumps(value))
            
            # handle numpy types → Python native
            elif isinstance(value, np.integer):
                record.append(int(value))
            
            elif isinstance(value, np.floating):
                record.append(float(value))
            
            elif isinstance(value, np.bool_):
                record.append(bool(value))
            
            else:
                record.append(value)
        
        records.append(tuple(record))
    
    return records


def reset_sequence(pg_conn, table_name, pk_column="id"):
    """
    Resets PostgreSQL sequence to max existing ID.
    Must run after inserting data with explicit IDs.
    """
    _init_schema_info()
    if table_name in schema_info["uuid_tables"]:
        # UUID tables do not have serial/sequence
        return
        
    cursor = pg_conn.cursor()
    try:
        # Step 1: get max id
        cursor.execute(f"SELECT COALESCE(MAX({pk_column}), 0) FROM {table_name};")
        max_id = cursor.fetchone()[0]
        
        # Step 2: check if sequence exists
        seq_name = f"{table_name}_{pk_column}_seq"
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = %s);", 
            (seq_name,)
        )
        seq_exists = cursor.fetchone()[0]
        
        if seq_exists:
            # Step 3: set sequence value
            # setval needs max_id + 1, or is_called=false
            cursor.execute(
                f"SELECT setval(%s, %s, false);", 
                (seq_name, max_id + 1)
            )
            pg_conn.commit()
            logger.info(f"Sequence reset for {table_name} to {max_id + 1}")
            
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"Failed to reset sequence for {table_name}: {e}")
        raise
        
    finally:
        cursor.close()


def load_table(pg_conn_or_holder, table_name, df, mysql_schema, schema_info_arg=None, is_first_chunk=True, is_last_chunk=True, chunk_number=1):
    """
    Complete load process for one table / chunk.
    1. Create table in PostgreSQL (on first chunk)
    2. Insert data (if data exists)
    3. Reset sequence (on last chunk)
    """
    global schema_info
    if schema_info_arg is not None:
        schema_info = schema_info_arg
    else:
        _init_schema_info()

    # Wrap connection in holder
    conn_holder = pg_conn_or_holder if isinstance(pg_conn_or_holder, ConnectionHolder) else ConnectionHolder(pg_conn_or_holder)

    # Step 1: create the table in PostgreSQL on first chunk
    if is_first_chunk:
        execute_with_retry(create_postgres_table, f"{table_name} CREATE TABLE", conn_holder, table_name, mysql_schema)

    # Step 2: insert transformed data if it is not None/empty
    row_count = 0
    if df is not None and not df.empty:
        row_count = insert_table_data(conn_holder, table_name, df, chunk_number=chunk_number)

    # Step 3: reset sequence only for non UUID tables on last chunk
    if is_last_chunk:
        if schema_info and "uuid_tables" in schema_info:
            if table_name not in schema_info["uuid_tables"]:
                execute_with_retry(reset_sequence, f"{table_name} RESET SEQUENCE", conn_holder, table_name)
        else:
            _init_schema_info()
            if table_name not in schema_info["uuid_tables"]:
                execute_with_retry(reset_sequence, f"{table_name} RESET SEQUENCE", conn_holder, table_name)

    return row_count


def load_all_tables(transformed_data, mysql_schemas):
    """
    Loads all 100 tables into PostgreSQL.
    """
    pg_conn = get_postgres_connection()
    
    total_rows = 0
    failed_tables = []
    
    try:
        # disable FK checks during load
        cursor = pg_conn.cursor()
        cursor.execute("SET session_replication_role = replica;")
        pg_conn.commit()
        cursor.close()
        logger.info("FK constraints disabled for bulk load")
        
        for table_name, df in transformed_data.items():
            try:
                rows = load_table(
                    pg_conn,
                    table_name,
                    df,
                    mysql_schemas[table_name]
                )
                total_rows += rows
                
            except Exception as e:
                logger.error(f"Failed to load {table_name}: {e}")
                failed_tables.append(table_name)
                continue
        
        # re-enable FK checks after load
        cursor = pg_conn.cursor()
        cursor.execute("SET session_replication_role = DEFAULT;")
        pg_conn.commit()
        cursor.close()
        logger.info("FK constraints re-enabled")
        
        logger.info(
            f"Load complete. "
            f"Total rows: {total_rows} | "
            f"Failed tables: {len(failed_tables)}"
        )
        
        if failed_tables:
            logger.warning(f"Failed tables: {failed_tables}")
        
        print("\n--- Adding Foreign Key Constraints ---")
        fk_success, fk_failed = add_foreign_keys(pg_conn)
        print(f"FK constraints added: {fk_success}")
        print(f"FK constraints failed: {len(fk_failed)}")
        
        return total_rows, failed_tables
        
    finally:
        pg_conn.close()


def add_foreign_keys(pg_conn, schema_info_arg=None):
    """
    Adds FK constraints after all data is loaded.
    Runs ALTER TABLE ADD CONSTRAINT for each relationship.
    """
    global schema_info
    if schema_info_arg is not None:
        schema_info = schema_info_arg
    else:
        _init_schema_info()

    cursor = pg_conn.cursor()
    success_count = 0
    failed_fks = []
    
    try:
        for child_table, child_col, parent_table, parent_col \
        in schema_info["foreign_keys"]:
            
            # generate unique constraint name
            constraint_name = (
                f"fk_{child_table}_{child_col}"
            )
            
            sql = f"""
                ALTER TABLE {child_table}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY ({child_col})
                REFERENCES {parent_table} ({parent_col});
            """
            
            try:
                cursor.execute(sql)
                pg_conn.commit()
                success_count += 1
                logger.info(
                    f"FK added: {child_table}.{child_col}"
                    f" → {parent_table}.{parent_col}"
                )
            
            except Exception as e:
                pg_conn.rollback()
                failed_fks.append(constraint_name)
                logger.warning(
                    f"FK failed: {constraint_name} | {e}"
                )
                raise
    
    finally:
        cursor.close()
    
    logger.info(
        f"FK constraints added: {success_count} | "
        f"Failed: {len(failed_fks)}"
    )
    
    if failed_fks:
        logger.warning(f"Failed FKs: {failed_fks}")
    
    return success_count, failed_fks