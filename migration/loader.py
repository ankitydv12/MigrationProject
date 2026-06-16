import psycopg2
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from config.db_config import get_postgres_connection, get_mysql_engine
from sqlalchemy import inspect
import logging
from utils.schema_analyzer import analyze_schema

logger = logging.getLogger(__name__)
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
        # extract length from VARCHAR(100) → VARCHAR(100)
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
        return "FLOAT"
    
    # default fallback
    logger.warning(
        f"Unknown type {type_str} in {table_name}.{col_name}"
        f" defaulting to TEXT"
    )
    return "TEXT"

def create_postgres_table(pg_conn, table_name, mysql_schema):
    """
    Creates a table in PostgreSQL based on MySQL schema.
    Drops table first if it already exists.
    
    mysql_schema comes from extract.get_table_schema()
    """
    cursor = pg_conn.cursor()
    
    try:
        # Step 1: drop table if exists
        # CASCADE drops dependent objects too
        cursor.execute(
            f"DROP TABLE IF EXISTS {table_name} CASCADE"
        )
        
        # Step 2: build column definitions
        columns = mysql_schema["columns"]
        pk_cols = mysql_schema["primary_key"]["constrained_columns"]
        
        col_definitions = []
        
        for col in columns:
            col_name = col["name"]
            pg_type  = map_mysql_type_to_postgres(
                col["type"], table_name, col_name
            )
            
            # handle nullable
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            
            # handle primary key with auto increment
            if col_name in pk_cols:
                if pg_type == "UUID":
                    # UUID primary key
                    col_def = (
                        f"{col_name} UUID PRIMARY KEY"
                    )
                else:
                    # integer primary key becomes SERIAL
                    col_def = (
                        f"{col_name} SERIAL PRIMARY KEY"
                    )
            else:
                col_def = f"{col_name} {pg_type} {nullable}"
            
            col_definitions.append(col_def)
        
        # Step 3: build CREATE TABLE statement
        cols_sql = ",\n    ".join(col_definitions)
        create_sql = (
            f"CREATE TABLE {table_name} (\n"
            f"    {cols_sql}\n"
            f");"
        )
        
        logger.info(f"Creating table: {table_name}")
        cursor.execute(create_sql)
        pg_conn.commit()
        logger.info(f"Table created: {table_name}")
        
    except Exception as e:
        pg_conn.rollback()
        logger.error(f"Failed to create {table_name}: {e}")
        raise
    
    finally:
        cursor.close()

from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
import json

def insert_table_data(pg_conn, table_name, df):
    """
    Inserts DataFrame into PostgreSQL table.
    Uses execute_values for bulk insert performance.
    """
    if df.empty:
        logger.warning(f"Empty DataFrame for {table_name}, skipping")
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
        # must handle special types before inserting
        records = prepare_records(df, table_name)
        
        # Step 4: bulk insert using execute_values
        # page_size controls how many rows per batch
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
            # pandas uses NaN and NaT for missing, PostgreSQL uses NULL
            if (isinstance(value, float) and np.isnan(value)) or value is pd.NaT:
                record.append(None)
            
            # handle pandas Timestamp → Python datetime
            elif isinstance(value, pd.Timestamp):
                record.append(value.to_pydatetime())
            
            # handle dict → JSON string for JSONB
            # psycopg2 needs json string for JSONB columns
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
    
    Without this: next INSERT will try id=1 and fail
    With this: next INSERT continues from max_id + 1
    """
    if table_name in schema_info["uuid_tables"]:
        logger.info(f"Skipping sequence reset for UUID table: {table_name}")
        return
        
    cursor = pg_conn.cursor()
    
    try:
        cursor.execute(f"""
            SELECT setval(
                pg_get_serial_sequence('{table_name}', '{pk_column}'),
                COALESCE(MAX({pk_column}), 1)
            )
            FROM {table_name};
        """)
        pg_conn.commit()
        logger.info(f"Sequence reset for {table_name}.{pk_column}")
        
    except Exception as e:
        pg_conn.rollback()
        # not all tables have sequences (UUID tables dont)
        # so just log warning, dont raise
        logger.warning(
            f"Sequence reset skipped for {table_name}: {e}"
        )
    
    finally:
        cursor.close()


def load_table(pg_conn, table_name, df, mysql_schema):
    """
    Complete load process for one table.
    1. Create table in PostgreSQL
    2. Insert data
    3. Reset sequence
    """
    # Step 1: create the table in PostgreSQL
    create_postgres_table(pg_conn, table_name, mysql_schema)

    # Step 2: insert transformed data
    row_count = insert_table_data(pg_conn, table_name, df)

    # Step 3: reset sequence only for non UUID tables
    # UUID tables dont have SERIAL so no sequence to reset
    if table_name not in schema_info["uuid_tables"]:
        reset_sequence(pg_conn, table_name)

    return row_count

def load_all_tables(transformed_data, mysql_schemas):
    """
    Loads all 100 tables into PostgreSQL.
    
    transformed_data = {"table_name": DataFrame}
    mysql_schemas    = {"table_name": schema_dict}
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
                continue   # skip failed table, continue others
        
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
        
                # after re-enabling FK checks add this:
        print("\n--- Adding Foreign Key Constraints ---")
        fk_success, fk_failed = add_foreign_keys(pg_conn)
        print(f"FK constraints added: {fk_success}")
        print(f"FK constraints failed: {len(fk_failed)}")
        
        return total_rows, failed_tables
        
    finally:
        pg_conn.close()


def add_foreign_keys(pg_conn):
    """
    Adds FK constraints after all data is loaded.
    Runs ALTER TABLE ADD CONSTRAINT for each relationship.
    """
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





if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    from migration.extract import extract_all_tables, get_table_schema
    from migration.transformer import transform_all_tables
    
    # Step 1: extract all
    print("\n--- Extracting all tables ---")
    extracted = extract_all_tables()
    
    # Step 2: get all schemas
    print("\n--- Getting all schemas ---")
    schemas = {
        table: get_table_schema(table) 
        for table in extracted.keys()
    }
    
    # Step 3: transform all
    print("\n--- Transforming all tables ---")
    transformed = transform_all_tables(extracted)
    
    # Step 4: load all
    print("\n--- Loading all tables ---")
    total_rows, failed = load_all_tables(transformed, schemas)
    
    print(f"\nTotal rows loaded: {total_rows}")
    print(f"Failed tables: {failed}")