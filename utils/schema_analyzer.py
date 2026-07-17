import sys
import os

# project_root sys.path fix same pattern as other files
project_root = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
sys.path.append(project_root)

from sqlalchemy import inspect
from graphlib import TopologicalSorter, CycleError
import logging
from config.db_config import get_mysql_engine

logger = logging.getLogger(__name__)


def get_all_foreign_keys():
    """
    Use SQLAlchemy inspector to read ALL tables.
    For each table, call inspector.get_foreign_keys(table).
    Returns a dict where:
      key = child table name
      value = set of parent table names it depends on.
    Tables with no FK dependencies get empty set().
    """
    x =0
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        # print("\n\n -------------------------Tables List Start -------------------------------\n\n")
        # print(tables)
        # print(len(tables))
        # print("\n\n -------------------------Tables List END -------------------------------\n\n")
        
        fk_graph = {}
        total_fks = 0
        for table in tables:       
            fk_graph[table] = set()
            fks = inspector.get_foreign_keys(table)
            """
            table = table_name
            .get_foreign_keys() = List of Dict 
            [{
            'name': 'addresses_ibfk_1', 
            'constrained_columns': ['region_id'], 
            'referred_schema': None, 
            'referred_table': 'regions', 
            'referred_columns': ['id'], 
            'options': {}
            }]
            """
            for fk in fks:
                referred = fk.get("referred_table")
                if referred:
                    fk_graph[table].add(referred)
                    total_fks += 1
        logger.info(f"Total FK relationships found: {total_fks}")
        # print("\n\n -------------------------Graph Start -------------------------------\n\n")
        # print(type(fk_graph))
        # for i,x in fk_graph.items():
        #     print(i,x)
        # print("\n\n-----------------------------Graph END---------------------------\n\n")
        return fk_graph
    except Exception as e:
        logger.error(f"Error in get_all_foreign_keys: {e}")
        raise
    finally:
        engine.dispose()

def get_migration_order():
    """
    Call get_all_foreign_keys() to build dependency graph.
    Use Python graphlib.TopologicalSorter to sort.
    TopologicalSorter takes the dependency dict directly.
    Call list(sorter.static_order()) to get ordered list.
    Return single ordered list of all 100 tables.
    """
    try:
        graph = get_all_foreign_keys()
        sorter = TopologicalSorter(graph)
        order = list(sorter.static_order())
        # print("+++++++++++++++++++++++++++++++++++++++Migration Order List++++++++++++++++++++\n\n")
        # print(order)
        # print("+++++++++++++++++++++++++++++++++++++++Migration Order List++++++++++++++++++++\n\n")

        logger.info(f"Final migration order determined (total tables: {len(order)})")
        return order
    except CycleError as e:
        msg = f"Circular dependency detected in table relationships: {e}"
        logger.error(msg)
        raise CycleError(msg) from e
    except Exception as e:
        logger.error(f"Error in get_migration_order: {e}")
        raise

def detect_uuid_tables():
    """
    Use SQLAlchemy inspector.
    For each table get primary key constraint columns.
    For each PK column get its type from get_columns().
    If type string contains VARCHAR and length is 36
    then this table uses UUID.
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        uuid_tables = []
        tables = inspector.get_table_names()
        for table in tables:
            pk_constraint = inspector.get_pk_constraint(table)
            # print(pk_constraint)
            """
            Return a dict which contain the primary key columns
            Ex: {'constrained_columns': ['id'], 'name': None}
            """
            pk_cols = pk_constraint.get("constrained_columns", [])
            """
                getting values(means primary col name ) of key constrained_columns() from dict 
            """
            if not pk_cols: 
                continue
            columns = inspector.get_columns(table)
            """
            [ 1. {'name': 'id', 'type': INTEGER(), 'default': None, 'comment': None, 'nullable': False, 'autoincrement': True},
             {'name': 'vin', 'type': VARCHAR(length=17), 'default': None, 'comment': None, 'nullable': False}, 
             {'name': 'license_plate', 'type': VARCHAR(length=20), 'default': None, 'comment': None, 'nullable': False},
              {'name': 'make', 'type': VARCHAR(length=50), 'default': None, 'comment': None, 'nullable': False}, 
              {'name': 'model', 'type': VARCHAR(length=50), 'default': None, 'comment': None, 'nullable': False},
               {'name': 'year', 'type': INTEGER(), 'default': None, 'comment': None, 'nullable': False, 'autoincrement': False},
                {'name': 'fuel_type', 'type': VARCHAR(length=20), 'default': None, 'comment': None, 'nullable': False},
                 {'name': 'payload_capacity_lbs', 'type': INTEGER(), 'default': None, 'comment': None, 'nullable': False, 'autoincrement': False},
                  {'name': 'created_at', 'type': TIMESTAMP(), 'default': 'CURRENT_TIMESTAMP', 'comment': None, 'nullable': True}] 
            """
            # print("+++++++++++++++++++++++++COLUMN NAMES ++++++++++++++++++++++++++++++++++++\n\n")
            # print(columns)
            # print("+++++++++++++++++++++++++COLUMN NAMES ++++++++++++++++++++++++++++++++++++ \n\n")

            pk_col_types = {col["name"]: str(col["type"]).upper() for col in columns if col["name"] in pk_cols}
            # print(pk_col_types)
            # {'id': 'VARCHAR(36)'}
            is_uuid = False
            for type_str in pk_col_types.values():
                if "VARCHAR" in type_str and "36" in type_str:
                    is_uuid = True
                    break
            if is_uuid:
                uuid_tables.append(table)
        logger.info(f"Detected UUID tables: {uuid_tables}")
        # print("+++++++++++++++++++++++++UUID TABLES ++++++++++++++++++++++++++++++++++++ \n\n")
        # print(uuid_tables)
        # print("+++++++++++++++++++++++++UUID TABLES ++++++++++++++++++++++++++++++++++++ \n\n")
        return uuid_tables
    except Exception as e:
        logger.error(f"Error in detect_uuid_tables: {e}")
        raise
    finally:
        engine.dispose()

def detect_json_columns():
    """
    Use SQLAlchemy inspector.
    For each table get all columns.
    If column type string contains JSON add to result dict.
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        json_cols_dict = {}
        tables = inspector.get_table_names()
        for table in tables:
            columns = inspector.get_columns(table)
            table_json_cols = []
            for col in columns:
                type_str = str(col["type"]).upper()
                if "JSON" in type_str:
                    table_json_cols.append(col["name"])
            if table_json_cols:
                json_cols_dict[table] = table_json_cols
        logger.info(f"Detected JSON columns: {json_cols_dict}")
        # print("+"*20 , "json_col_dict","-"*20)
        # print(json_cols_dict)
        return json_cols_dict
    except Exception as e:
        logger.error(f"Error in detect_json_columns: {e}")
        raise
    finally:
        engine.dispose()

def detect_boolean_columns():
    """
    Use SQLAlchemy inspector.
    For each table get all columns.
    If column type string contains TINYINT(1) OR BOOL add to result dict.
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        boolean_cols_dict = {}
        total_bool_cols = 0
        tables = inspector.get_table_names()
        for table in tables:
            columns = inspector.get_columns(table)
            table_bool_cols = []
            for col in columns:
                col_type = col["type"]
                type_str = str(col_type).upper()
                if "TINYINT(1)" in type_str or "BOOL" in type_str or ("TINYINT" in type_str and getattr(col_type, "display_width", None) == 1):
                    table_bool_cols.append(col["name"])
            if table_bool_cols:
                boolean_cols_dict[table] = table_bool_cols
                total_bool_cols += len(table_bool_cols)
        logger.info(f"Total boolean columns detected across all tables: {total_bool_cols}")
        # print("---------------------------------------boolean_col_dict________________________________")
        # print(boolean_cols_dict)
        # print("---------------------------------------boolean_col_dict________________________________")
        return boolean_cols_dict

    except Exception as e:
        logger.error(f"Error in detect_boolean_columns: {e}")
        raise
    finally:
        engine.dispose()

def get_foreign_key_definitions():
    """
    Use SQLAlchemy inspector.
    For each table call inspector.get_foreign_keys(table).
    Each FK gives you:
      constrained_columns: the child column names
      referred_table: the parent table name
      referred_columns: the parent column names
    Returns list of tuples:
      (child_table, child_column, parent_table, parent_column)
    """
    engine = get_mysql_engine()
    try:
        inspector = inspect(engine)
        fk_definitions = []
        tables = inspector.get_table_names()
        for table in tables:
            fks = inspector.get_foreign_keys(table)
            for fk in fks:
                parent_table = fk["referred_table"]
                for child_col, parent_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                    fk_definitions.append((table, child_col, parent_table, parent_col))
        logger.info(f"Total FK definitions found: {len(fk_definitions)}")
        # print("+++++++++++++++++++++++++Foreign Key Definitions++++++++++++++++++++++++++++++++++++ \n\n")
        # print(fk_definitions)
        # print("+++++++++++++++++++++++++Foreign Key Definitions++++++++++++++++++++++++++++++++++++ \n\n")
        return fk_definitions
    except Exception as e:
        logger.error(f"Error in get_foreign_key_definitions: {e}")
        raise
    finally:
        engine.dispose()

_cached_schema_info = None

def analyze_schema():
    """
    Master function that calls ALL functions above once.
    Returns single dict with all information:
      {
        "migration_order"  : [...ordered list of 100 tables...],
        "foreign_keys"     : [...list of FK tuples...],
        "uuid_tables"      : [...list of UUID table names...],
        "json_columns"     : {...dict of table: [columns]...},
        "boolean_columns"  : {...dict of table: [columns]...}
      }
    """
    global _cached_schema_info
    if _cached_schema_info is not None:
        return _cached_schema_info
        
    try:
        migration_order = get_migration_order()
        foreign_keys = get_foreign_key_definitions()
        uuid_tables = detect_uuid_tables()
        json_columns = detect_json_columns()
        boolean_columns = detect_boolean_columns()
        
        _cached_schema_info = {
            "migration_order": migration_order,
            "foreign_keys": foreign_keys,
            "uuid_tables": uuid_tables,
            "json_columns": json_columns,
            "boolean_columns": boolean_columns
        }
        # for k , v in _cached_schema_info.items():
        #     print(k , "     \n",v)
        #     print()
        
        logger.info(
            f"Schema analysis complete. Summary:\n"
            f"  - Total tables found: {len(migration_order)}\n"
            f"  - Total FK relationships: {len(foreign_keys)}\n"
            f"  - UUID tables: {len(uuid_tables)}\n"
            f"  - JSON column tables: {len(json_columns)}\n"
            f"  - Boolean column tables: {len(boolean_columns)}"
        )
        #print(_cached_schema_info)
        return _cached_schema_info
    except Exception as e:
        logger.error(f"Error in analyze_schema: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logging.disable(logging.CRITICAL)
    
    schema_info = analyze_schema()
    
    print("\n=== SCHEMA ANALYSIS RESULTS ===")
    print(f"Migration order (first 10): "
          f"{schema_info['migration_order'][:10]}")
    print(f"Total FK relationships: "
          f"{len(schema_info['foreign_keys'])}")
    print(f"UUID tables: "
          f"{schema_info['uuid_tables']}")
    print(f"JSON column tables: "
          f"{list(schema_info['json_columns'].keys())}")
    print(f"Boolean column tables: "
          f"{len(schema_info['boolean_columns'])} tables")
