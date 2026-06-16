
import os
import sys
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

import pandas as pd
import logging
from config.db_config import get_mysql_engine , get_postgres_connection

logger = logging.getLogger(__name__)

def get_mysql_row_counts():
    engine = get_mysql_engine()
    try:
        query = """
                SELECT 
                    table_name ,
                    table_row as row_count
                FROM Information_schema.tables
                Where table_schema = DATABASE()
        """

        df = pd.read_sql_query(query,engine)
        counts = dict(zip(df["table_name"],df['row_count']))
        logger.info(f"Mysql Row Count {len(counts)}")
        return counts
    finally:
        engine.dispose()


def get_postgres_row_count(table_names):
    conn = get_postgres_connection()
    cursor = conn.cursor()
    counts = {}
    try:
        for table in table_names:
            cursor.execute("""
                Select count(*) from {}
            """.format(table))
        count = cursor.fetchone()[0]
        counts[table] = count
        
        logger.info(f"PostgreSQL row counts fetched "
                   f"for {len(counts)} tables")
        return counts
    
    finally:
        cursor.close()
        conn.close()


def validate_row_counts(mysql_counts, pg_counts):
    """
    Compares row counts between MySQL and PostgreSQL.
    Returns validation results as list of dicts.
    """
    results = []
    
    for table_name, mysql_count in mysql_counts.items():
        pg_count = pg_counts.get(table_name, 0)
        
        # compare counts
        status = "PASS" if mysql_count == pg_count else "FAIL"
        
        results.append({
            "table_name"  : table_name,
            "mysql_rows"  : mysql_count,
            "pg_rows"     : pg_count,
            "difference"  : abs(mysql_count - pg_count),
            "status"      : status
        })
        
        if status == "FAIL":
            logger.warning(
                f"MISMATCH: {table_name} | "
                f"MySQL={mysql_count} | "
                f"PG={pg_count}"
            )
        else:
            logger.info(f"PASS: {table_name} | rows={pg_count}")
    
    return results
        


def generate_report(validation_results):
    """
    Generates CSV report and prints summary to terminal.
    Saves to reports/validation_report.csv
    """
    # build dataframe from results
    df = pd.DataFrame(validation_results)
    
    # summary statistics
    total   = len(df)
    passed  = len(df[df['status'] == 'PASS'])
    failed  = len(df[df['status'] == 'FAIL'])
    
    # save to CSV
    report_path = os.path.join(
        project_root, "reports", "validation_report.csv"
    )
    df.to_csv(report_path, index=False)
    
    # print summary
    print("\n" + "="*50)
    print("MIGRATION VALIDATION REPORT")
    print("="*50)
    print(f"Total Tables  : {total}")
    print(f"Passed        : {passed}")
    print(f"Failed        : {failed}")
    print(f"Success Rate  : {(passed/total)*100:.1f}%")
    print("="*50)
    
    # print("\nJSON Column Checks:")
    # for r in json_results:
    #     print(f"  {r['table']}.{r['column']} "
    #           f"→ {r['type']} → {r['status']}")
    
    # if failed > 0:
    #     print("\nFailed Tables:")
    #     failed_df = df[df['status'] == 'FAIL']
    #     for _, row in failed_df.iterrows():
    #         print(f"  {row['table_name']} | "
    #               f"MySQL={row['mysql_rows']} | "
    #               f"PG={row['pg_rows']}")
    
    print(f"\nFull report saved: {report_path}")
    logger.info(f"Validation report saved to {report_path}")
    
    return passed == total

def run_validation():
    """
    Master validation function.
    Calls all validation functions in order.
    Returns True if all passed, False if any failed.
    """
    logger.info("Starting validation...")
    
    # Step 1: get mysql counts
    mysql_counts = get_mysql_row_counts()
    
    # Step 2: get postgres counts
    # pass table names from mysql_counts
    pg_counts = get_postgres_row_count(list(mysql_counts.keys()))
    
    # Step 3: compare counts
    validation_results = validate_row_counts(mysql_counts, pg_counts)
    

    
    # Step 5: generate report
    success = generate_report(validation_results)
    
    return success