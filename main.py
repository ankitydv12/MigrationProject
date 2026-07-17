import sys
import os
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

from utils.schema_analyzer import analyze_schema
from migration.extract import extract_all_tables, get_table_schema
from migration.transformer import transform_all_tables
from migration.loader import load_all_tables
from validation.Validate import run_validation

def main():
    print("\n" + "="*50)
    print("MYSQL TO POSTGRESQL MIGRATION PIPELINE")
    print("="*50)
    
    # Analyze schema once at the start of the pipeline
    schema_info = analyze_schema()
    
    # Print summary of what was auto-detected
    print("\n=== AUTO-DETECTED SCHEMA SUMMARY ===")
    print(f"Total tables found           : {len(schema_info['migration_order'])}")
    print(f"Total FK relationships       : {len(schema_info['foreign_keys'])}")
    print(f"UUID tables detected         : {len(schema_info['uuid_tables'])} {schema_info['uuid_tables']}")
    print(f"JSON column tables detected  : {len(schema_info['json_columns'])} {list(schema_info['json_columns'].keys())}")
    print(f"Boolean column tables detected: {len(schema_info['boolean_columns'])}")
    print("="*50)
    
    # Step 1: Extract
    print("\n--- Step 1: Extracting from MySQL ---")
    extracted = extract_all_tables()
    """
    {
        "table" : "df"
    }
    """
    # Step 2: Get schemas
    print("\n--- Step 2: Reading schemas ---")
    schemas = {
        table: get_table_schema(table)
        for table in extracted.keys()
    }
    """
    {
        "table_name": {"table_name" : table_name,
            "columns"    : columns,
            "primary_key": pk,
            "foreign_keys": fks}
        .
        .
        .
    }
    """
    
    # Step 3: Transform
    print("\n--- Step 3: Transforming data ---")
    transformed = transform_all_tables(extracted)
    
    # Step 4: Load
    print("\n--- Step 4: Loading to PostgreSQL ---")
    total_rows, failed = load_all_tables(transformed, schemas)
    
    # Step 5: Validate
    print("\n--- Step 5: Validating migration ---")
    success = run_validation()
    
    # Final summary
    print("\n" + "="*50)
    print("PIPELINE COMPLETE")
    print(f"Total rows migrated : {total_rows}")
    print(f"Failed tables       : {len(failed)}")
    print(f"Validation          : {'PASSED' if success else 'FAILED'}")
    print("="*50)

if __name__ == "__main__":
    main()