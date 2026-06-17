import sys
import os

# add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(
        "MySQL to PostgreSQL Migration Tool"
    )
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())