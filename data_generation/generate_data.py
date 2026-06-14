import sys
import os
import json
import mysql.connector

# Load the parent generate_data.py module dynamically to prevent recursive import conflicts
import importlib.util
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_gen_path = os.path.join(parent_dir, "generate_data.py")
spec = importlib.util.spec_from_file_location("parent_generate_data", parent_gen_path)
pg_gen = importlib.util.module_from_spec(spec)
sys.modules["parent_generate_data"] = pg_gen
spec.loader.exec_module(pg_gen)

# Define MySQL configuration
MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123",
    "database": "migration_db",
}

def connect_db():
    """Establishes and returns a connection to the MySQL server."""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"]
        )
        return conn
    except Exception as e:
        print(f"[FAIL] Connection to MySQL failed: {e}")
        raise e

def check_and_initialize_schema(conn):
    """Checks if the database and required tables exist in MySQL. If not, runs schema.sql."""
    cursor = conn.cursor()
    try:
        # Check if database exists
        cursor.execute("SHOW DATABASES LIKE %s", (MYSQL_CONFIG["database"],))
        db_exists = cursor.fetchone()
        
        table_count = 0
        if db_exists:
            # Switch to database
            cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
            cursor.execute("SHOW TABLES")
            table_count = len(cursor.fetchall())
            
        if not db_exists or table_count < 100:
            print(f"MySQL Schema status: exists={bool(db_exists)}, tables={table_count}. Expected 100 tables.")
            print("Initializing MySQL schema from schema.sql...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.join(script_dir, "schema.sql")
            with open(schema_path, "r", encoding="utf-8") as f:
                sql = f.read()
            
            # Split SQL file by semicolons, filtering out comments and empty statements
            statements = []
            current_stmt = []
            for line in sql.splitlines():
                stripped = line.strip()
                if stripped.startswith("--") or not stripped:
                    continue
                current_stmt.append(line)
                if stripped.endswith(";"):
                    statements.append("\n".join(current_stmt))
                    current_stmt = []
                    
            for stmt in statements:
                stmt_str = stmt.strip()
                if stmt_str:
                    cursor.execute(stmt_str)
            conn.commit()
            print("[OK] MySQL Schema and tables initialized successfully.")
        else:
            print(f"[OK] MySQL Schema has {table_count} tables. Ready for data generation.")
            # Ensure database is selected
            cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] MySQL Schema verification/initialization failed: {e}")
        raise e
    finally:
        cursor.close()

def truncate_tables(conn):
    """Truncates all tables in the schema using FOREIGN_KEY_CHECKS to allow multiple runs."""
    cursor = conn.cursor()
    try:
        cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f"TRUNCATE TABLE `{table}`")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        print("[OK] All existing MySQL tables truncated successfully.")
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] MySQL Truncation failed: {e}")
        raise e
    finally:
        cursor.close()

def insert_batch(conn, query, data, table_name):
    """Inserts a batch of rows in MySQL using optimized multi-row INSERTs."""
    if not data:
        return
    cursor = conn.cursor()
    
    # query is like: "INSERT INTO countries (name, iso_code) VALUES %s"
    # We replace "VALUES %s" with multi-row placeholders: "VALUES (%s, %s), (%s, %s)..."
    parts = query.split(" VALUES ")
    if len(parts) != 2:
        parts = query.split(" values ")
    prefix = parts[0]
    num_cols = len(data[0])
    
    chunk_size = 1000
    try:
        # Switch to database just in case
        cursor.execute(f"USE `{MYSQL_CONFIG['database']}`")
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size]
            row_placeholder = "(" + ", ".join(["%s"] * num_cols) + ")"
            placeholders = ", ".join([row_placeholder] * len(chunk))
            mysql_query = f"{prefix} VALUES {placeholders}"
            
            # Flatten the chunk values
            flat_vals = []
            for row in chunk:
                # Replace dict/list with json string for MySQL JSON columns
                processed_row = []
                for val in row:
                    if isinstance(val, (dict, list)):
                        processed_row.append(json.dumps(val))
                    else:
                        processed_row.append(val)
                flat_vals.extend(processed_row)
                
            cursor.execute(mysql_query, flat_vals)
        conn.commit()
        print(f"[OK] Inserted {len(data):,} rows into {table_name}")
    except Exception as e:
        conn.rollback()
        print(f"[FAIL] Failed to insert rows into {table_name}: {e}")
        raise e
    finally:
        cursor.close()

# Monkeypatch the module level function references in pg_gen
pg_gen.connect_db = connect_db
pg_gen.check_and_initialize_schema = check_and_initialize_schema
pg_gen.truncate_tables = truncate_tables
pg_gen.insert_batch = insert_batch

if __name__ == "__main__":
    pg_gen.main()
