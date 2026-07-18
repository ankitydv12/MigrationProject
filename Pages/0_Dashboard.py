import streamlit as st
from utils.schema_analyzer import analyze_schema

st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
    layout="wide"
)

st.title("🗄️ MySQL → PostgreSQL Migration Dashboard")

st.markdown(
    """
Welcome to the **MySQL ➜ PostgreSQL Migration Tool**.

This application helps migrate data from a MySQL database to PostgreSQL
using an ETL (Extract → Transform → Load) pipeline.
"""
)

st.divider()

# ---------------- Schema Information ---------------- #

try:
    schema_info = analyze_schema()

    migration_order = schema_info["migration_order"]
    foreign_keys = schema_info["foreign_keys"]
    uuid_tables = schema_info["uuid_tables"]
    json_columns = schema_info["json_columns"]
    boolean_columns = schema_info["boolean_columns"]

    total_tables = len(migration_order)

    dependent_tables = len(
        set(fk[0] for fk in foreign_keys)
    )

    independent_tables = total_tables - dependent_tables

except Exception as e:
    st.error(f"Unable to analyze schema.\n\n{e}")
    st.stop()

# ---------------- Metrics ---------------- #

st.subheader("📈 Database Summary")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Tables", total_tables)
col2.metric("Independent Tables", independent_tables)
col3.metric("Dependent Tables", dependent_tables)
col4.metric("Foreign Keys", len(foreign_keys))

st.divider()

col5, col6, col7 = st.columns(3)

col5.metric("UUID Tables", len(uuid_tables))
col6.metric("JSON Tables", len(json_columns))
col7.metric("Boolean Tables", len(boolean_columns))

st.divider()

# ---------------- Migration Progress ---------------- #

st.subheader("📊 Migration Status")

if "migration_result" in st.session_state:

    result = st.session_state["migration_result"]

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Rows Migrated",
        result["rows"]
    )

    col2.metric(
        "Failed Tables",
        len(result["failed_tables"])
    )

    if result["validation"]:
        status = "PASS"
    else:
        status = "Not Run"

    col3.metric(
        "Validation",
        status
    )

else:

    st.info("No migration has been executed yet.")

st.divider()

# ---------------- Migration Order ---------------- #

st.subheader("🧩 Migration Order Preview")

preview = migration_order[:15]

for i, table in enumerate(preview, start=1):
    st.write(f"{i}. {table}")

if len(migration_order) > 15:
    st.info(
        f"... and {len(migration_order)-15} more tables."
    )

st.divider()

# ---------------- Project Workflow ---------------- #

st.subheader("🔄 Migration Workflow")

st.markdown("""
1. **Configure Database Connections**
2. **Analyze MySQL Schema**
3. **Run Migration**
4. **Validate Data**
5. **View Migration Logs**
""")

st.divider()

st.success("Dashboard loaded successfully.")