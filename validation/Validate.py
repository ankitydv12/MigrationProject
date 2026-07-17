import os
import sys
import pandas as pd
import numpy as np
import json
import logging
import time
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from config.db_config import get_mysql_engine, get_postgres_connection
import config

logger = logging.getLogger(__name__)

def compare_values(v1, v2):
    """
    Compares two values from MySQL and PostgreSQL, aligning types and allowing minor floats delta.
    """
    is_v1_null = (v1 is None or pd.isna(v1) or v1 is pd.NaT)
    is_v2_null = (v2 is None or pd.isna(v2) or v2 is pd.NaT)
    
    if is_v1_null and is_v2_null:
        return True
    if is_v1_null or is_v2_null:
        return False
        
    # Booleans
    if isinstance(v1, bool) or isinstance(v2, bool):
        return bool(v1) == bool(v2)
        
    # Numeric comparison (mixed floats and integers)
    if isinstance(v1, (int, float, np.number)) and isinstance(v2, (int, float, np.number)):
        try:
            return np.isclose(float(v1), float(v2), atol=1e-5, rtol=1e-5)
        except Exception:
            pass
            
    # Dict/JSON comparison
    if isinstance(v1, dict) or isinstance(v2, dict):
        try:
            d1 = v1 if isinstance(v1, dict) else json.loads(str(v1))
            d2 = v2 if isinstance(v2, dict) else json.loads(str(v2))
            return d1 == d2
        except Exception:
            pass
            
    # Date/datetime comparison
    if isinstance(v1, (pd.Timestamp, datetime)) or isinstance(v2, (pd.Timestamp, datetime)):
        try:
            t1 = pd.Timestamp(v1).isoformat()
            t2 = pd.Timestamp(v2).isoformat()
            return t1 == t2
        except Exception:
            pass
            
    # Default string representation comparison
    return str(v1) == str(v2)


def validate_sequences(pg_conn):
    """
    Validates PostgreSQL sequence positions.
    Returns a dictionary mapping table name to sequence info and correctness status.
    """
    cursor = pg_conn.cursor()
    seq_results = {}
    try:
        # Get all sequences attached to columns default values
        cursor.execute("""
            SELECT 
                t.relname AS table_name,
                a.attname AS column_name,
                s.relname AS seq_name
            FROM pg_class s
            JOIN pg_depend d ON d.objid = s.oid
            JOIN pg_class t ON d.refobjid = t.oid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
            WHERE s.relkind = 'S' AND t.relkind = 'r';
        """)
        sequences = cursor.fetchall()
        for tbl, col, seq in sequences:
            # Query sequence current status
            cursor.execute(f'SELECT last_value, is_called FROM "{seq}"')
            last_value, is_called = cursor.fetchone()
            next_value = last_value if not is_called else (last_value + 1)
            
            # Query max id from table
            cursor.execute(f'SELECT COALESCE(MAX("{col}"), 0) FROM "{tbl}"')
            max_id = cursor.fetchone()[0]
            
            is_correct = next_value >= (max_id + 1)
            seq_results[tbl] = {
                "column": col,
                "seq_name": seq,
                "next_value": next_value,
                "max_id": max_id,
                "is_correct": is_correct
            }
        return seq_results
    except Exception as e:
        logger.error(f"Error validating sequences: {e}")
        return {}
    finally:
        cursor.close()


def generate_comprehensive_report(results, duration):
    """
    Generates CSV report and prints summary to terminal.
    Saves to reports/validation_report.csv
    """
    df = pd.DataFrame(results)
    
    total = len(df)
    passed = len(df[df['status'] == 'PASS'])
    failed = len(df[df['status'] == 'FAIL'])
    
    report_path = os.path.join(
        project_root, "reports", "validation_report.csv"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    df.to_csv(report_path, index=False)
    
    print("\n" + "="*50)
    print("MIGRATION VALIDATION REPORT")
    print("="*50)
    print(f"Tables Validated    : {total}")
    print(f"Passed              : {passed}")
    print(f"Failed              : {failed}")
    print(f"Validation Duration : {duration:.2f} sec")
    print(f"Success Rate        : {(passed/total)*100:.1f}%" if total > 0 else "Success Rate        : 100.0%")
    print("="*50)
    
    if failed > 0:
        print("\nFailed Tables:")
        failed_df = df[df['status'] == 'FAIL']
        for _, row in failed_df.iterrows():
            print(f"  {row['table_name']} | Reason: {row['reason']}")
            
    print(f"\nFull report saved: {report_path}")
    logger.info(f"Validation report saved to {report_path}")
    
    return failed == 0


def run_validation():
    """
    Master validation function.
    Runs counts, keys, NULLs, sequences, and sample row validations.
    """
    logger.info("Starting comprehensive data integrity validation...")
    start_time = time.perf_counter()
    
    mysql_engine = get_mysql_engine()
    pg_conn = get_postgres_connection()
    
    validation_results = []
    
    sample_enabled = getattr(config, "ENABLE_SAMPLE_VALIDATION", False)
    sample_size = getattr(config, "VALIDATION_SAMPLE_SIZE", 100)
    
    try:
        from sqlalchemy import inspect
        mysql_inspector = inspect(mysql_engine)
        mysql_tables = mysql_inspector.get_table_names()
        
        # 1. Fetch PostgreSQL sequence positions
        seq_info = validate_sequences(pg_conn)
        
        for table in mysql_tables:
            table_failed = False
            failure_reasons = []
            
            # Step 1: Row count validation
            mysql_count_df = pd.read_sql_query(f"SELECT COUNT(*) as cnt FROM {table}", mysql_engine)
            mysql_row_count = int(mysql_count_df['cnt'].iloc[0])
            
            pg_cursor = pg_conn.cursor()
            pg_cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            pg_row_count = pg_cursor.fetchone()[0]
            pg_cursor.close()
            
            if mysql_row_count != pg_row_count:
                table_failed = True
                failure_reasons.append(f"Row Count Mismatch (MySQL={mysql_row_count}, PG={pg_row_count})")
                
            # Step 2: Primary Key count comparison
            pk_constraint = mysql_inspector.get_pk_constraint(table)
            pk_cols = pk_constraint.get('constrained_columns', [])
            
            if pk_cols:
                pk_col = pk_cols[0]
                
                # MySQL PK count
                mysql_pk_df = pd.read_sql_query(f"SELECT COUNT({pk_col}) as cnt FROM {table}", mysql_engine)
                mysql_pk_count = int(mysql_pk_df['cnt'].iloc[0])
                
                # PG PK count
                pg_cursor = pg_conn.cursor()
                pg_cursor.execute(f'SELECT COUNT("{pk_col}") FROM "{table}"')
                pg_pk_count = pg_cursor.fetchone()[0]
                pg_cursor.close()
                
                if mysql_pk_count != pg_pk_count:
                    table_failed = True
                    failure_reasons.append(f"PK Count Mismatch (MySQL={mysql_pk_count}, PG={pg_pk_count})")
                    
            # Step 3: NULL count comparison for every nullable column
            columns = mysql_inspector.get_columns(table)
            nullable_cols = [c['name'] for c in columns if c['nullable']]
            
            for col in nullable_cols:
                # MySQL Null count
                mysql_null_df = pd.read_sql_query(f"SELECT COUNT(*) as cnt FROM {table} WHERE {col} IS NULL", mysql_engine)
                mysql_null_count = int(mysql_null_df['cnt'].iloc[0])
                
                # PG Null count
                pg_cursor = pg_conn.cursor()
                pg_cursor.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" IS NULL')
                pg_null_count = pg_cursor.fetchone()[0]
                pg_cursor.close()
                
                if mysql_null_count != pg_null_count:
                    table_failed = True
                    failure_reasons.append(f"NULL Count Mismatch on column {col} (MySQL={mysql_null_count}, PG={pg_null_count})")
                    
            # Step 4: PostgreSQL sequence validation
            if table in seq_info:
                seq_check = seq_info[table]
                if not seq_check["is_correct"]:
                    table_failed = True
                    failure_reasons.append(f"Sequence Incorrect (next_value={seq_check['next_value']}, max_id={seq_check['max_id']})")
                    
            # Step 5: Optional Sample Validation
            if sample_enabled and not table_failed and pk_cols:
                pk_col = pk_cols[0]
                sample_pks_df = pd.read_sql_query(f"SELECT {pk_col} FROM {table} ORDER BY RAND() LIMIT {sample_size}", mysql_engine)
                
                if not sample_pks_df.empty:
                    pk_vals = sample_pks_df[pk_col].tolist()
                    placeholders = ", ".join(["%s"] * len(pk_vals))
                    
                    # Fetch rows from MySQL
                    mysql_samples = pd.read_sql_query(f"SELECT * FROM {table} WHERE {pk_col} IN ({placeholders})", mysql_engine, params=tuple(pk_vals))
                    # Fetch rows from PG
                    pg_samples = pd.read_sql_query(f'SELECT * FROM "{table}" WHERE "{pk_col}" IN ({placeholders})', pg_conn, params=tuple(pk_vals))
                    
                    # Align by sorting
                    mysql_samples = mysql_samples.sort_values(by=pk_col).reset_index(drop=True)
                    pg_samples = pg_samples.sort_values(by=pk_col).reset_index(drop=True)
                    
                    mismatch_found = False
                    for idx in range(len(mysql_samples)):
                        mysql_row = mysql_samples.iloc[idx]
                        pk_val = mysql_row[pk_col]
                        
                        pg_row_matches = pg_samples[pg_samples[pk_col] == pk_val]
                        if pg_row_matches.empty:
                            mismatch_found = True
                            failure_reasons.append(f"Sample row with PK={pk_val} not found in Postgres")
                            break
                            
                        pg_row = pg_row_matches.iloc[0]
                        for col_item in mysql_samples.columns:
                            m_val = mysql_row[col_item]
                            p_val = pg_row[col_item]
                            
                            if not compare_values(m_val, p_val):
                                mismatch_found = True
                                failure_reasons.append(f"Sample mismatch on column {col_item} for PK={pk_val} (MySQL={m_val}, PG={p_val})")
                                break
                        if mismatch_found:
                            break
                            
                    if mismatch_found:
                        table_failed = True
                        
            status = "FAIL" if table_failed else "PASS"
            reason = "; ".join(failure_reasons) if table_failed else "All checks passed"
            
            validation_results.append({
                "table_name": table,
                "status": status,
                "reason": reason
            })
            
            if status == "FAIL":
                logger.warning(f"Validation FAILED for {table}: {reason}")
            else:
                logger.info(f"Validation PASSED for {table}")
                
        duration = time.perf_counter() - start_time
        success = generate_comprehensive_report(validation_results, duration)
        return success
        
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        return False
    finally:
        mysql_engine.dispose()
        pg_conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    success = run_validation()
    
    if success:
        print("\n[OK] Migration validated successfully")
    else:
        print("\n[FAIL] Validation failed - check report")