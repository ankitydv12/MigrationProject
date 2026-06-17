import sys
import os
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import mysql.connector
import psycopg2

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QFormLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox,
    QProgressBar
)
from PyQt5.QtCore import pyqtSignal, QThread, Qt
from PyQt5.QtGui import QFont


# background thread for testing connections
class ConnectionTestWorker(QThread):
    success = pyqtSignal(str)
    failure = pyqtSignal(str)
    
    def __init__(self, db_type, host, port,
                 user, password, database):
        super().__init__()
        self.db_type  = db_type
        self.host     = host
        self.port     = int(port)
        self.user     = user
        self.password = password
        self.database = database
    
    def run(self):
        print(f"[THREAD] run() called for {self.db_type}")
        try:
            if self.db_type == "mysql":
                import pymysql
                print("[THREAD] Connecting with pymysql...")
                conn = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    connect_timeout=5
                )
                cursor = conn.cursor()
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                print(f"[THREAD] MySQL OK: {version}")
                self.success.emit(f"MySQL OK: {version}")
            
            elif self.db_type == "postgres":
                import psycopg2
                print("[THREAD] Connecting to PostgreSQL...")
                conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    dbname=self.database,
                    connect_timeout=5
                )
                conn.close()
                print("[THREAD] PostgreSQL OK")
                self.success.emit("PostgreSQL OK")
        
        except Exception as e:
            import traceback
            error = traceback.format_exc()
            print(f"[THREAD] ERROR:\n{error}")
            self.failure.emit(str(e))


class ConnectionScreen(QWidget):
    
    # emits both SQLAlchemy engines to MainWindow
    connected = pyqtSignal(object, object)
    
    def __init__(self):
        super().__init__()
        self._mysql_ok    = False
        self._postgres_ok = False
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 30, 40, 30)
        
        # title
        title = QLabel(
            "Database Connection Configuration"
        )
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # two panels side by side
        panels = QHBoxLayout()
        panels.addWidget(self._build_mysql_panel())
        panels.addWidget(self._build_postgres_panel())
        layout.addLayout(panels)
        
        # status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # progress bar hidden by default
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        
        # buttons row
        btn_row = QHBoxLayout()
        
        self.test_btn = QPushButton("Test Connections")
        self.test_btn.setMinimumHeight(40)
        self.test_btn.clicked.connect(
            self._on_test_btn_clicked
        )
        print("[UI] Test button created and connected")
        
        self.connect_btn = QPushButton("Connect & Continue")
        self.connect_btn.setMinimumHeight(40)
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._connect)
        
        btn_row.addWidget(self.test_btn)
        btn_row.addWidget(self.connect_btn)
        layout.addLayout(btn_row)
    
    def _build_mysql_panel(self):
        group = QGroupBox("MySQL Source Database")
        form  = QFormLayout(group)
        
        self.mysql_host = QLineEdit("localhost")
        self.mysql_port = QLineEdit("3306")
        self.mysql_user = QLineEdit("root")
        self.mysql_pass = QLineEdit()
        self.mysql_pass.setEchoMode(QLineEdit.Password)
        self.mysql_db   = QLineEdit("migration_db")
        
        form.addRow("Host:",     self.mysql_host)
        form.addRow("Port:",     self.mysql_port)
        form.addRow("User:",     self.mysql_user)
        form.addRow("Password:", self.mysql_pass)
        form.addRow("Database:", self.mysql_db)
        
        return group
    
    def _build_postgres_panel(self):
        group = QGroupBox("PostgreSQL Target Database")
        form  = QFormLayout(group)
        
        self.pg_host = QLineEdit("localhost")
        self.pg_port = QLineEdit("5432")
        self.pg_user = QLineEdit("postgres")
        self.pg_pass = QLineEdit()
        self.pg_pass.setEchoMode(QLineEdit.Password)
        self.pg_db   = QLineEdit("migrated_db")
        
        form.addRow("Host:",     self.pg_host)
        form.addRow("Port:",     self.pg_port)
        form.addRow("User:",     self.pg_user)
        form.addRow("Password:", self.pg_pass)
        form.addRow("Database:", self.pg_db)
        
        return group
    
    def _on_test_btn_clicked(self):
        print("[UI] Button click received")
        self._test_connections()

    def _test_connections(self):
        print("[UI] Test button clicked")
        self._mysql_ok    = False
        self._postgres_ok = False
        self.connect_btn.setEnabled(False)
        self.test_btn.setEnabled(False)
        self.progress.show()
        self.status_label.setText(
            "Testing MySQL connection..."
        )
        
        print("[UI] Creating worker...")
        self.mysql_worker = ConnectionTestWorker(
            "mysql",
            self.mysql_host.text().strip(),
            self.mysql_port.text().strip(),
            self.mysql_user.text().strip(),
            self.mysql_pass.text(),
            self.mysql_db.text().strip()
        )
        print("[UI] Worker created")
        print("[UI] Connecting signals...")
        self.mysql_worker.success.connect(self._on_mysql_success)
        self.mysql_worker.failure.connect(self._on_test_failure)
        print("[UI] Signals connected")
        print("[UI] Starting thread...")
        self.mysql_worker.start()
        print("[UI] Thread started")
        print(f"[UI] Thread running: {self.mysql_worker.isRunning()}")
    
    def _on_mysql_success(self, msg):
        self._mysql_ok = True
        self.status_label.setText(
            f"✓ {msg}\nTesting PostgreSQL..."
        )
        
        # now test PostgreSQL
        self.pg_worker = ConnectionTestWorker(
            "postgres",
            self.pg_host.text().strip(),
            self.pg_port.text().strip(),
            self.pg_user.text().strip(),
            self.pg_pass.text(),
            self.pg_db.text().strip()
        )
        self.pg_worker.success.connect(
            self._on_postgres_success
        )
        self.pg_worker.failure.connect(
            self._on_test_failure
        )
        self.pg_worker.start()
    
    def _on_postgres_success(self, msg):
        self._postgres_ok = True
        self.progress.hide()
        self.test_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.status_label.setText(
            "✓ MySQL connected\n✓ PostgreSQL connected\n"
            "Both databases ready. Click Connect to continue."
        )
    
    def _on_test_failure(self, error):
        self.progress.hide()
        self.test_btn.setEnabled(True)
        self.status_label.setText(f"✗ {error}")
        QMessageBox.critical(
            self, "Connection Failed", error
        )
    
    def _connect(self):
        """Creates SQLAlchemy engines and emits signal."""
        try:
            from config.db_config import (
                get_mysql_engine_from_params,
                get_postgres_engine_from_params
            )
            
            mysql_engine = get_mysql_engine_from_params(
                self.mysql_host.text().strip(),
                int(self.mysql_port.text().strip()),
                self.mysql_user.text().strip(),
                self.mysql_pass.text(),
                self.mysql_db.text().strip()
            )
            
            pg_engine = get_postgres_engine_from_params(
                self.pg_host.text().strip(),
                int(self.pg_port.text().strip()),
                self.pg_user.text().strip(),
                self.pg_pass.text(),
                self.pg_db.text().strip()
            )
            
            self.connected.emit(mysql_engine, pg_engine)
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "Engine Creation Failed",
                str(e)
            )