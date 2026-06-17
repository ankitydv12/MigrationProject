from PyQt5.QtCore import QThread, pyqtSignal

class MigrationWorker(QThread):
    log_message = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, mysql_engine, postgres_engine):
        # Initialize engines.
        super().__init__()
        self.mysql_engine, self.postgres_engine = mysql_engine, postgres_engine

    def run(self):
        # Run migration steps.
        try:
            info = self._step1()
            ext, sch = self._step2(info)
            trans = self._step3(info, ext)
            rows, failed = self._step4(info, trans, sch)
            self._step5(info, rows, failed)
        except Exception:
            import traceback
            self.error.emit(traceback.format_exc())

    def _step1(self):
        # Step 1: Analyze schema.
        self.log_message.emit("Analyzing schema...")
        from utils.schema_analyzer import analyze_schema
        info = analyze_schema()
        self.log_message.emit(f"Found {len(info['migration_order'])} tables")
        self.progress.emit(5)
        return info

    def _step2(self, info):
        # Step 2: Extract tables.
        self.log_message.emit("Extracting tables from MySQL...")
        from migration.extract import extract_table_data, get_table_schema
        total = len(info['migration_order'])
        extracted, schemas = {}, {}
        for i, table in enumerate(info['migration_order']):
            extracted[table] = extract_table_data(table, engine=self.mysql_engine)
            schemas[table] = get_table_schema(table, engine=self.mysql_engine)
            self.log_message.emit(f"Extracted: {table}")
            self.progress.emit(5 + int((i + 1) / total * 25))
        return extracted, schemas

    def _step3(self, info, ext):
        # Step 3: Transform data.
        self.log_message.emit("Transforming data...")
        from migration.transformer import transform_table
        total = len(info['migration_order'])
        trans = {}
        for i, table in enumerate(info['migration_order']):
            trans[table] = transform_table(ext[table], table, info)
            self.progress.emit(30 + int((i + 1) / total * 20))
        return trans

    def _step4(self, info, trans, sch):
        # Step 4: Load data.
        self.log_message.emit("Loading to PostgreSQL...")
        from migration.loader import load_table, add_foreign_keys
        pg_conn = self.postgres_engine.raw_connection()
        cur = pg_conn.cursor()
        cur.execute("SET session_replication_role = replica;")
        pg_conn.commit()
        cur.close()
        total_rows, failed, total = 0, [], len(info['migration_order'])
        for i, table in enumerate(info['migration_order']):
            try:
                rows = load_table(pg_conn, table, trans[table], sch[table], info)
                total_rows += rows
                self.log_message.emit(f"Loaded: {table} ({rows:,} rows)")
            except Exception as e:
                failed.append(table)
                self.log_message.emit(f"FAILED: {table}: {e}")
            self.progress.emit(50 + int((i + 1) / total * 30))
        cur = pg_conn.cursor()
        cur.execute("SET session_replication_role = DEFAULT;")
        pg_conn.commit()
        cur.close()
        add_foreign_keys(pg_conn, info)
        pg_conn.close()
        return total_rows, failed

    def _step5(self, info, rows, failed):
        # Step 5: Validate migration.
        self.log_message.emit("Validating migration...")
        from validation.Validate import get_mysql_row_counts, get_postgres_row_count, validate_row_counts, generate_report
        my_c = get_mysql_row_counts(self.mysql_engine)
        pg_c = get_postgres_row_count(list(my_c.keys()), self.postgres_engine)
        res = validate_row_counts(my_c, pg_c)
        generate_report(res)
        passed = sum(1 for r in res if r["status"] == "PASS")
        self.log_message.emit(f"Validation: {passed}/{len(res)} tables passed")
        self.progress.emit(100)
        self.finished.emit({"total_rows": rows, "total_tables": len(info['migration_order']), "failed_tables": failed, "validated": passed == len(res)})
