import streamlit as st

from log.logging_config import setup_logging
setup_logging()
# ----------------------------------------
# Configure Logging
# ----------------------------------------
import logging
import sys


logger = logging.getLogger(__name__)

def handle_exception(exc_type, exc_value, exc_traceback):

    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(
            exc_type,
            exc_value,
            exc_traceback
        )
        return

    logger.exception(
        "Unhandled Exception",
        exc_info=(
            exc_type,
            exc_value,
            exc_traceback
        )
    )

sys.excepthook = handle_exception

# ----------------------------------------
# Streamlit Configuration
# ----------------------------------------

st.set_page_config(
    page_title="MySQL → PostgreSQL Migration",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------------------
# Navigation Pages
# ----------------------------------------

pages = [

    st.Page(
        "pages/0_Dashboard.py",
        title="Dashboard",
        icon="📊"
    ),

    st.Page(
        "pages/1_Database_Connection.py",
        title="Connections",
        icon="🔗"
    ),

    st.Page(
        "pages/2_Schema_Analysis.py",
        title="Schema Analysis",
        icon="🧩"
    ),

    st.Page(
        "pages/3_Migration.py",
        title="Migration",
        icon="🔄"
    ),

    st.Page(
        "pages/4_Validation.py",
        title="Validation",
        icon="✅"
    ),

    st.Page(
        "pages/5_Logs.py",
        title="Logs",
        icon="📜"
    )

]

# ----------------------------------------
# Sidebar
# ----------------------------------------

st.sidebar.title("🗄️ Migration Tool")

st.sidebar.markdown(
    """
### MySQL ➜ PostgreSQL

This application performs a complete ETL migration.

### Workflow

1. Dashboard
2. Database Connection
3. Schema Analysis
4. Migration
5. Validation
6. Logs
"""
)

st.sidebar.divider()

st.sidebar.info(
    "Developed using Python, Streamlit, Pandas, SQLAlchemy and PostgreSQL."
)

# ----------------------------------------
# Run Selected Page
# ----------------------------------------

navigation = st.navigation(pages)

navigation.run()