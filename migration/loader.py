import psycopg2
import sys
import os
import logging
from sqlalchemy import inspect
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
import json

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


def insert_table_data(pg_conn, table_name, df):
    """
    Inserts DataFrame into PostgreSQL table.
    Uses execute_values for bulk insert performance.
    """
    if df is None or df.empty:
        logger.warning(f"Empty/None DataFrame for {table_name}, skipping insert")
        return 0
    
    cursor = pg_conn.cursor()
    
    try:
        # Step 1: get column names from DataFrame
        columns = list(df.columns)
        
        # Step 2: build INSERT statement
        cols_str = ", ".join(columns)
        insert_sql = (
            f"INSERT INTO {table_name} ({cols_str}) "
            f"VALUES %s"
        )
        
        # Step 3: convert DataFrame to list of tuples
        records = prepare_records(df, table_name)
        
        # Step 4: bulk insert using execute_values
        execute_values(
            cursor,
            insert_sql,
            records,
            page_size=1000
        )
        
        pg_conn.commit()
        logger.info(
            f"Inserted {len(records)} rows into {table_name}"
        )
        return len(records)
        
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"Insert failed for {table_name}: {e}")
        raise
        
    finally:
        cursor.close()

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
        
    finally:
        cursor.close()


def load_table(pg_conn, table_name, df, mysql_schema, schema_info_arg=None, is_first_chunk=True, is_last_chunk=True):
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

    # Step 1: create the table in PostgreSQL on first chunk
    if is_first_chunk:
        create_postgres_table(pg_conn, table_name, mysql_schema)

    # Step 2: insert transformed data if it is not None/empty
    row_count = 0
    if df is not None and not df.empty:
        row_count = insert_table_data(pg_conn, table_name, df)

    # Step 3: reset sequence only for non UUID tables on last chunk
    if is_last_chunk:
        if schema_info and "uuid_tables" in schema_info:
            if table_name not in schema_info["uuid_tables"]:
                reset_sequence(pg_conn, table_name)
        else:
            _init_schema_info()
            if table_name not in schema_info["uuid_tables"]:
                reset_sequence(pg_conn, table_name)

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
    
    finally:
        cursor.close()
    
    logger.info(
        f"FK constraints added: {success_count} | "
        f"Failed: {len(failed_fks)}"
    )
    
    if failed_fks:
        logger.warning(f"Failed FKs: {failed_fks}")
    
    return success_count, failed_fks