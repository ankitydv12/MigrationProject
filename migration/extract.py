import sys
import os
import logging

# Ensure the project root is in the Python search path.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from config.db_config import get_mysql_engine
from sqlalchemy import inspect
from utils.schema_analyzer import analyze_schema
import pandas as pd

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

def get_all_table_names():
    """
    Returns list of all table names in MySQL database.
    Uses SQLAlchemy inspector - no raw SQL needed.
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        logging.info(f"Tables are found and no is {len(table_names)}")
        return table_names        
    except Exception as e:
        logging.error(f"Failed to get tables name --> {e}")
    finally:
        engine.dispose()

def get_table_schema(table_name):
    """
    Retrieves columns and foreign keys for a single table.
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name)
        fkeys = inspector.get_foreign_keys(table_name)
        return {
            "columns": columns,
            "foreign_keys": fkeys
        }
    except Exception as e:
        logging.error(f"Failed to get schema for {table_name} : {e}")
    finally:
        engine.dispose()

def get_migration_order():
    """
    Returns the dynamic migration order from schema analysis.
    """
    _init_schema_info()
    migration_order = schema_info["migration_order"]
    logger.info(f"Migration order loaded dynamically: {len(migration_order)} tables")
    return migration_order

def extract_table_data(table_name, chunksize=None, engine=None):
    """
    Extracts data from a single MySQL table.
    Yields data as pandas DataFrame chunks.
    
    Uses chunksize to avoid loading entire table in memory.
    """
    import config
    if chunksize is None:
        chunksize = getattr(config, "CHUNK_SIZE", 5000)

    if engine is None:
        engine = get_mysql_engine()
        should_dispose = True
    else:
        should_dispose = False
    try:
        logging.info(f"Extracting rows from {table_name}")
        chunk_iterator = pd.read_sql_table(table_name, engine, chunksize=chunksize)
        for i, chunk in enumerate(chunk_iterator):
            logging.info(f"{table_name} chunk: {i+1} | {len(chunk)} row Extracted.....")
            yield chunk
    except Exception as e:
        logging.error(f"Extraction Fail for {table_name} : {e}")
        raise
    finally:
        if should_dispose:
            engine.dispose()

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    # Test 1 - table names
    tables = get_all_table_names()
    print(f"Total tables found: {len(tables)}")
    
    # Test 2 - schema of one table
    schema = get_table_schema("customers")
    print(f"Customers columns: {len(schema['columns'])}")
    print(f"Customers FK: {schema['foreign_keys']}")
    
    # Test 3 - extract one table only
    df_generator = extract_table_data("customers")
    try:
        df = next(df_generator)
        print(f"Customers rows in first chunk: {len(df)}")
        print(df.head(3))
    except StopIteration:
        print("Customers table is empty")
    
    # Test 4 - migration order
    order = get_migration_order()
    print(f"Migration order (first 10): {order[:10]}")
    print(f"Total tables in migration order: {len(order)}")
