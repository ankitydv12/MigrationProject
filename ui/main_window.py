from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QLineEdit, QPushButton, QProgressBar, QTextEdit, QMessageBox
)
from sqlalchemy import create_engine
from ui.migration_worker import MigrationWorker

def _create_mysql_engine(host, port, user, password, database):
    # Create MySQL engine.
    url = f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True, connect_args={"use_pure": True})

def _create_postgres_engine(host, port, user, password, database):
    # Create PostgreSQL engine.
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True, pool_size=5)

class MainWindow(QMainWindow):
    def __init__(self):
        # Initialize MainWindow and construct visual elements.
        super().__init__()
        self.setWindowTitle("MySQL to PostgreSQL Migration Tool")
        self.setMinimumSize(850, 650)
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        top = QHBoxLayout()
        self.m_grp, self.m_in = self._form("MySQL Settings", [("Host", "localhost"), ("Port", "3306"), ("User", "root"), ("Password", ""), ("Database", "migration_db")])
        self.p_grp, self.p_in = self._form("PostgreSQL Settings", [("Host", "localhost"), ("Port", "5432"), ("User", "postgres"), ("Password", ""), ("Database", "migrated_db")])
        top.addWidget(self.m_grp)
        top.addWidget(self.p_grp)
        layout.addLayout(top)
        self.btn = QPushButton("Connect & Migrate")
        self.btn.setFixedHeight(45)
        self.btn.clicked.connect(self._start)
        layout.addWidget(self.btn)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(250)
        layout.addWidget(self.log)
        self.statusBar().showMessage("Ready")

    def _form(self, title, fields):
        # Dynamically build credentials form.
        grp = QGroupBox(title)
        lay = QFormLayout(grp)
        inputs = {}
        for label, default in fields:
            edit = QLineEdit(default)
            if label == "Password":
                edit.setEchoMode(QLineEdit.Password)
            lay.addRow(label, edit)
            inputs[label.lower()] = edit
        return grp, inputs

    def _start(self):
        # Handle Connect & Migrate button action.
        m = {k: v.text() for k, v in self.m_in.items()}
        p = {k: v.text() for k, v in self.p_in.items()}
        self.btn.setEnabled(False)
        self.log.clear()
        self.statusBar().showMessage("Starting migration...")
        my_eng = _create_mysql_engine(m['host'], m['port'], m['user'], m['password'], m['database'])
        pg_eng = _create_postgres_engine(p['host'], p['port'], p['user'], p['password'], p['database'])
        self.worker = MigrationWorker(my_eng, pg_eng)
        self.worker.log_message.connect(self.log.append)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, result):
        # Handle worker success signal.
        self.btn.setEnabled(True)
        self.statusBar().showMessage("Migration complete.")
        msg = f"Migration finished successfully!\nTotal rows: {result.get('total_rows', 0)}\nTotal tables: {result.get('total_tables', 0)}"
        QMessageBox.information(self, "Success", msg)

    def _on_error(self, err_msg):
        # Handle worker error signal.
        self.btn.setEnabled(True)
        self.log.append(f"ERROR: {err_msg}")
        self.statusBar().showMessage("Migration failed.")