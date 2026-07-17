import sys
import os
import logging
import json
import pandas as pd
import uuid as uuid_lib

# Ensure the project root is in the Python search path.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from migration.extract import extract_table_data
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

def transform_json_columns(df, table_name):
    """
    Converts JSON string columns to Python dicts.
    psycopg2 will handle dict → PostgreSQL JSONB correctly.
    """
    _init_schema_info()
    columns_to_convert = schema_info["json_columns"].get(table_name, [])
    
    for col in columns_to_convert:
        if col in df.columns:
            def safe_parse(value):
                if value is None:
                    return None
                if isinstance(value, dict):
                    return value      # already parsed
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        f"{table_name}.{col} has invalid "
                        f"JSON value: {value}"
                    )
                    return None       # return None for bad JSON
            
            df[col] = df[col].apply(safe_parse)
            logger.info(f"JSON converted: {table_name}.{col}")
    
    return df

def transform_boolean_columns(df, table_name):
    """
    Converts TINYINT(1) integer columns to Python bool.
    0 → False, 1 → True
    """
    _init_schema_info()
    # Step 1: get list of boolean columns for this table
    columns_to_convert = schema_info["boolean_columns"].get(table_name, [])
    
    # Step 2: loop through each column
    for col in columns_to_convert:
        if col in df.columns:
            # Step 3: convert to bool
            # handle None/NaN values carefully
            df[col] = df[col].apply(
                lambda x: bool(x) if pd.notna(x) else None
            ).astype(object)
            logger.info(f"Boolean converted: {table_name}.{col}")
    
    return df

def transform_uuid_columns(df, table_name):
    """
    Validates UUID format in UUID primary key tables.
    MySQL stores as VARCHAR(36), PostgreSQL needs valid UUID string.
    """
    _init_schema_info()
    if table_name not in schema_info["uuid_tables"]:
        return df
    
    def validate_uuid(value):
        if value is None:
            return None
        try:
            # this validates format and returns clean UUID string
            return str(uuid_lib.UUID(str(value)))
        except ValueError:
            logger.warning(
                f"{table_name} has invalid UUID: {value}"
            )
            return value    # return as is if validation fails
    
    if "id" in df.columns:
        df["id"] = df["id"].apply(validate_uuid)
        logger.info(f"UUID validated: {table_name}.id")
    
    return df

def transform_table(df, table_name, schema_info_arg=None):
    """
    Master transformation function.
    Applies all necessary transformations for a given table.
    Returns clean DataFrame ready for PostgreSQL.
    """
    global schema_info
    if schema_info_arg is not None:
        schema_info = schema_info_arg
    else:
        _init_schema_info()

    # Note: Operates safely on both full tables and DataFrame chunks independently.
    logger.info(f"Transforming table: {table_name}")
    
    # Step 1: apply JSON transformation if needed
    df = transform_json_columns(df, table_name) 
    
    # Step 2: apply boolean transformation if needed
    df = transform_boolean_columns(df, table_name)
    
    # Step 3: apply UUID transformation if needed
    df = transform_uuid_columns(df, table_name)
    
    logger.info(f"Transformation complete: {table_name} "
               f"| rows: {len(df)}")
    
    return df

def transform_all_tables(extracted_data):
    """
    Takes the full dict from extractor.
    Returns transformed dict ready for loader.
    
    extracted_data = {"table_name": DataFrame, ...}
    transformed_data = {"table_name": DataFrame, ...}
    """
    transformed_data = {}
    
    for table_name, df in extracted_data.items():
        transformed_data[table_name] = transform_table(df, table_name)
    
    logger.info(f"All tables transformed: {len(transformed_data)}")
    return transformed_data

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # Test 1 - JSON transformation
    print("\n--- Testing JSON transformation ---")
    df = next(extract_table_data("audit_logs"))
    df_transformed = transform_table(df, "audit_logs")
    print(f"old_values type after transform: "
          f"{type(df_transformed['old_values'].iloc[0])}")
    
    # Test 2 - Boolean transformation
    print("\n--- Testing Boolean transformation ---")
    df = next(extract_table_data("payment_methods"))
    df_transformed = transform_table(df, "payment_methods")
    print(f"is_active type after transform: "
          f"{type(df_transformed['is_active'].iloc[0])}")
    
    # Test 3 - UUID transformation
    print("\n--- Testing UUID transformation ---")
    df = next(extract_table_data("employees"))
    df_transformed = transform_table(df, "employees")
    print(f"UUID sample: {df_transformed['id'].iloc[0]}")