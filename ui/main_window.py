import sys
import os
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget, QMessageBox
)

from ui.connection_screen import ConnectionScreen
# from ui.table_selection_screen import TableSelectionScreen
# from ui.migration_screen import MigrationScreen

# screen index constants
SCREEN_CONNECTION = 0
SCREEN_TABLES     = 1
SCREEN_MIGRATION  = 2

class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(
            "MySQL to PostgreSQL Migration Tool"
        )
        self.setMinimumSize(900, 650)
        
        # engines stored here and passed between screens
        self.mysql_engine    = None
        self.postgres_engine = None
        
        # stack holds all three screens
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # create screens
        self.connection_screen = ConnectionScreen()
        # self.table_screen      = TableSelectionScreen()
        # self.migration_screen  = MigrationScreen()
        
        # add to stack in order
        self.stack.addWidget(self.connection_screen)
        # self.stack.addWidget(self.table_screen)
        # self.stack.addWidget(self.migration_screen)
        
        # connect signals
        self.connection_screen.connected.connect(
            self._on_connected
        )
        # self.table_screen.tables_selected.connect(
        #     self._on_tables_selected
        # )
        # self.migration_screen.migration_done.connect(
        #     self._on_migration_done
        # )
        
        # start on connection screen
        self.stack.setCurrentIndex(SCREEN_CONNECTION)
        self.statusBar().showMessage(
            "Step 1: Configure database connections"
        )
    
    def _on_connected(self, mysql_engine, postgres_engine):
        """Called when connection screen verifies both DBs."""
        self.mysql_engine    = mysql_engine
        self.postgres_engine = postgres_engine
        
        # pass mysql engine to table selection screen
        self.table_screen.set_source_engine(mysql_engine)
        
        # move to table selection screen
        self.stack.setCurrentIndex(SCREEN_TABLES)
        self.statusBar().showMessage(
            "Step 2: Select tables to migrate"
        )
    
    def _on_tables_selected(self, tables, options):
        """Called when user selects tables and clicks start."""
        # configure migration screen
        self.migration_screen.configure(
            self.mysql_engine,
            self.postgres_engine,
            tables,
            options
        )
        
        # move to migration screen
        self.stack.setCurrentIndex(SCREEN_MIGRATION)
        self.statusBar().showMessage(
            "Step 3: Migration in progress..."
        )
    
    def _on_migration_done(self, result):
        """Called when migration finishes."""
        status = "PASSED" if result.get(
            "validated", False
        ) else "COMPLETED"
        
        self.statusBar().showMessage(
            f"Migration {status} | "
            f"Rows: {result.get('total_rows', 0):,} | "
            f"Tables: {result.get('total_tables', 0)}"
        )
        
        QMessageBox.information(
            self,
            "Migration Complete",
            f"Migration finished successfully!\n\n"
            f"Total rows migrated : "
            f"{result.get('total_rows', 0):,}\n"
            f"Total tables        : "
            f"{result.get('total_tables', 0)}\n"
            f"Failed tables       : "
            f"{len(result.get('failed_tables', []))}\n"
            f"Validation          : {status}"
        )