"""
100 tables × 10,000 rows = 1,000,000 rows total
Each table is fall between small and medium so ----> pandas + Sql Alchemy  is perfect 

20 ecommerce tables    - FK relationships, migration order known
80 independent tables  - no FK, migrate in any order
JSONB columns          - identified in IT and CMS modules
UUID columns           - employees, invoices, api_keys, certificates
10k rows per table     - all same size, simple strategy

Revised Simple Strategy for extractor.py
Since all tables are 10k rows:
Schema extraction     →  SQLAlchemy Inspector
Data extraction       →  pandas read_sql_table
                         chunksize = 1000
                         simple and clean
Special handling      →  JSON columns  → json.loads()
                         UUID columns  → str() casting

------------------------------------extract.py --------------------------
Function 1: get_all_table_names()
Function 2: get_table_schema()
Function 3: extract_table_data()
Function 4: get_migration_order()
            (handles FK ordering for 20 ecommerce tables)


What extractor.py Does
Only one responsibility - read from MySQL. It never writes anything. It never transforms anything. Just reads and returns data.
extractor.py reads:
1. All table names
2. Schema of each table (columns, types, PKs, FKs)
3. Actual data from each table
4. Migration order for FK dependent tables    

"""


"""
Here We have to Import get_mysql_connection() from the config 
we have to provide root folder to the python so it get the file 

"""


import sys
import os

# Get the absolute path of the project root
# __file__ is the current file (table_profiler.py)
# os.path.dirname goes one level up (utils folder)
# os.path.dirname again goes one more level up (project root)

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Add project root to Python's search path
sys.path.append(project_root)

# Now this works
from config.db_config import get_mysql_engine
from sqlalchemy import inspect
import logging

logging.getLogger(__name__)


def get_all_table_names():
    """
    Returns list of all table names in MySQL database.
    Uses SQLAlchemy inspector - no raw SQL needed.
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        logging.info(f"Tables are found and no is  {len(table_names)}")
        return table_names        

    except Exception as e:
        logging.error("Failed to get tables name --> {e}")
    finally:
        engine.dispose()
        """
        Why do we call engine.dispose() in finally block and not connection.close()?
        Think about it. Answer: SQLAlchemy engine manages a connection pool, not a single connection. dispose() closes all pooled connections cleanly.
        """
"""
Function 2 - get_table_schema()
This is important. It reads schema of one table and returns it as a structured dict.
"""
#This is what transformer.py will use later to convert MySQL types to PostgreSQL types.
def get_table_schema(table_name):
    """
    Returns schema details of a single table.
    Returns dict with columns, primary keys, foreign keys.
    """
    engine = get_mysql_engine()
    
    try:
        inspector = inspect(engine)
        
        # get columns - returns list of dicts
        # each dict has: name, type, nullable, default
        columns = inspector.get_columns(table_name)
        
        # get primary key
        pk = inspector.get_pk_constraint(table_name)
        
        # get foreign keys
        fks = inspector.get_foreign_keys(table_name)
        
        schema = {
            "table_name" : table_name,
            "columns"    : columns,
            "primary_key": pk,
            "foreign_keys": fks
        }
        
        logging.info(f"Schema extracted for table: {table_name}")
        return schema
    
    except Exception as e:
        logging.error(f"Failed to get schema for {table_name}: {e}")
        raise
    
    finally:
        engine.dispose()

"""
Function 3 - get_migration_order()
This is the most important function for your 20 ecommerce tables. It defines which table migrates first based on FK dependencies.
python
"""
def get_migration_order():
    """
    Returns two separate lists:
    1. Ordered list of 20 ecommerce tables (FK dependency order)
    2. List of 80 independent tables (any order)
    
    Ecommerce tables must migrate parent before child.
    """
    
    # Hardcode the ecommerce order based on your ER diagram
    # You already know this from the ER details file
    ecommerce_ordered = [
        # Level 0 - no dependencies
        "countries",
        "suppliers", 
        "products",
        "product_categories",
        "payment_methods",
        "coupons",
        
        # Level 1 - depends on level 0
        "regions",
        "product_variants",
        "supplier_products",
        
        # Level 2 - depends on level 1
        "addresses",
        "inventory",
        
        # Level 3 - depends on level 2
        "customers",
        
        # Level 4 - depends on level 3
        "orders",
        "carts",
        "coupon_usage",
        "reviews",
        
        # Level 5 - depends on level 4
        "order_items",
        "payments",
        "shipment_tracking",
        "cart_items"
    ]

    all_tables = get_all_table_names()
    independent_tables = {t for t in all_tables if t not in ecommerce_ordered}

    logging.info(f"Ecommer Tables : {len(ecommerce_ordered)}")
    logging.info(f"Independe Tables  : {len(independent_tables)}")
    return ecommerce_ordered, independent_tables


# Function 4 - extract_table_data()
# This is the core extraction function. Every table goes through this.
import pandas as pd 
def extract_table_data(table_name, chunksize=1000):
    """
    Extracts data from a single MySQL table.
    Returns data as pandas DataFrame chunks.
    
    Uses chunksize to avoid loading entire table in memory.
    For 10k rows with chunksize=1000, gives 10 chunks of 1000 rows each.
    """
    engine = get_mysql_engine()
    try:
        logging.info(f"Extracting rows from  {table_name}")
        chunks = []
        chunk_iterator = pd.read_sql_table(table_name,engine,chunksize=chunksize)

        for i , chunk in enumerate(chunk_iterator):
            chunks.append(chunk)
            logging.info(f"{table_name} chunk: {i+1} | {len(chunk)} row Extracted.....")

        full_df = pd.concat(chunks,ignore_index=True)
        logging.info(f"Total rows extracted from " f"{table_name}: {len(full_df)}")
        return full_df

    except Exception as e:
        logging.error(f"Extraction Fail for {table_name} : {e}")
    finally:
        engine.dispose()

def extract_all_tables():
    """
    Extracts all 100 tables in correct order.
    Returns a dict where key=table_name, value=dataframe
    
    Hint - structure to build:
    {
        "customers": DataFrame(...),
        "orders": DataFrame(...),
        ...all 100 tables...
    }
    """
    #Step 1 : Get migration order 
    ecommers_tables , independent_tables = get_migration_order() 

    #Step 2 : Combine 
    all_tables_ordered  = ecommers_tables + independent_tables

    #step 3 : loop through and extract each table
    extracted_data = {}

    for table_name in all_tables_ordered:
        extracted_data[table_name] = extract_table_data(table_name)

    logging.info(f"Extraction complete. "
               f"Total tables extracted: {len(extracted_data)}")

    return extracted_data        


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
    df = extract_table_data("customers")
    print(f"Customers rows: {len(df)}")
    print(df.head(3))
    
    # Test 4 - migration order
    ec, ind = get_migration_order()
    print(f"Ecommerce order: {ec}")
    print(f"Independent count: {len(ind)}")   
