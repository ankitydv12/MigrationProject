import time
import logging

from migration.extract import (
    get_migration_order,
    get_table_schema,
    extract_table_data,
)
from migration.transformer import transform_table
from migration.loader import (
    load_table,
    add_foreign_keys,
    ConnectionHolder,
)

from config.db_config import get_postgres_connection
from utils.schema_analyzer import analyze_schema

logger = logging.getLogger(__name__)


def run_migration(
    progress_callback=None,
    status_callback=None,
    table_callback=None,
):
    """
    Run complete migration.
    """

    start_time = time.time()

    if status_callback:
        status_callback("Analyzing Schema")

    schema_info = analyze_schema()
    migration_order = get_migration_order()

    total_tables = len(migration_order)

    pg_conn = get_postgres_connection()
    conn_holder = ConnectionHolder(pg_conn)

    total_rows = 0
    failed_tables = []

    try:
        cursor = pg_conn.cursor()
        cursor.execute("SET session_replication_role = replica;")
        pg_conn.commit()
        cursor.close()

        for table_index, table_name in enumerate(migration_order):

            if status_callback:
                status_callback("Migrating Tables")

            if table_callback:
                table_callback(table_name)

            logger.info(f"Starting table: {table_name}")

            mysql_schema = get_table_schema(table_name)

            try:

                chunks = list(extract_table_data(table_name))

                total_chunks = len(chunks)

                if total_chunks == 0:
                    logger.warning(f"{table_name} is empty")

                for chunk_index, chunk in enumerate(chunks):

                    transformed_df = transform_table(chunk, table_name, schema_info)
                    print(type(transformed_df))
                    print(transformed_df)
                    rows = load_table(
                        conn_holder,
                        table_name,
                        transformed_df,
                        mysql_schema,
                        schema_info_arg=schema_info,
                        is_first_chunk=(chunk_index == 0),
                        is_last_chunk=(chunk_index == total_chunks - 1),
                        chunk_number=chunk_index + 1,
                    )

                    total_rows += rows

            except Exception as e:

                logger.exception(
                    f"Failed migrating {table_name}"
                )

                failed_tables.append(table_name)

            if progress_callback:

                percent = int(
                    ((table_index + 1) / total_tables) * 100
                )

                progress_callback(percent)

        if status_callback:
            status_callback("Adding Foreign Keys")

        cursor = pg_conn.cursor()
        cursor.execute("SET session_replication_role = DEFAULT;")
        pg_conn.commit()
        cursor.close()

        add_foreign_keys(
            pg_conn,
            schema_info
        )

        if status_callback:
            status_callback("Migration Completed")

        return {
            "tables": total_tables,
            "rows": total_rows,
            "failed_tables": failed_tables,
            "time": round(time.time() - start_time, 2),
        }

    except Exception:

        logger.exception("Migration Failed")
        raise

    finally:
        pg_conn.close()