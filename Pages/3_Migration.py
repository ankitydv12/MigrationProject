import time
import streamlit as st

from streamlit_utils.migration_runner import run_migration

# -------------------------------------------------
# Page Config
# -------------------------------------------------

st.set_page_config(
    page_title="Migration",
    page_icon="🔄",
    layout="wide"
)

# -------------------------------------------------
# Session State
# -------------------------------------------------

if "migration_result" not in st.session_state:
    st.session_state.migration_result = None

if "migration_running" not in st.session_state:
    st.session_state.migration_running = False

if "migration_progress" not in st.session_state:
    st.session_state.migration_progress = 0

if "migration_status" not in st.session_state:
    st.session_state.migration_status = "Waiting to start..."

if "current_table" not in st.session_state:
    st.session_state.current_table = "-"

if "elapsed_time" not in st.session_state:
    st.session_state.elapsed_time = 0

# -------------------------------------------------
# Title
# -------------------------------------------------

st.title("🔄 MySQL ➜ PostgreSQL Migration")

st.markdown("""
This page performs the complete migration process.

### Migration Steps

1. Analyze Schema
2. Extract Data
3. Transform Data
4. Load Data
5. Add Foreign Keys

Click **Start Migration** to begin.
""")

st.divider()

# -------------------------------------------------
# Progress Section
# -------------------------------------------------

st.subheader("Migration Progress")

progress_bar = st.progress(
    st.session_state.migration_progress
)

col1, col2, col3 = st.columns(3)

col1.metric(
    "Progress",
    f"{st.session_state.migration_progress}%"
)

col2.metric(
    "Elapsed Time",
    f"{st.session_state.elapsed_time} sec"
)

col3.metric(
    "Status",
    "Running"
    if st.session_state.migration_running
    else "Idle"
)

st.info(
    f"Current Stage : {st.session_state.migration_status}"
)

st.info(
    f"Current Table : {st.session_state.current_table}"
)

st.divider()

# -------------------------------------------------
# Clear Log File
# -------------------------------------------------

with open("logs/migration.log", "w", encoding="utf-8"):
    pass

# -------------------------------------------------
# Start Migration
# -------------------------------------------------

if st.button(
    "▶ Start Migration",
    type="primary",
    use_container_width=True,
    disabled=st.session_state.migration_running
):

    st.session_state.migration_running = True
    st.session_state.migration_result = None
    st.session_state.migration_progress = 0
    st.session_state.current_table = "-"
    st.session_state.migration_status = "Initializing..."

    start_time = time.time()

    def update_progress(percent):
        st.session_state.migration_progress = percent
        st.session_state.elapsed_time = int(
            time.time() - start_time
        )
        progress_bar.progress(percent)

    def update_status(message):
        st.session_state.migration_status = message

    def update_table(table):
        st.session_state.current_table = table

    try:

        result = run_migration(
            progress_callback=update_progress,
            status_callback=update_status,
            table_callback=update_table
        )

        st.session_state.migration_result = result
        st.session_state.migration_running = False
        st.session_state.migration_progress = 100
        st.session_state.migration_status = "Migration Completed"

        st.rerun()

    except Exception as e:

        st.session_state.migration_running = False
        st.session_state.migration_status = "Migration Failed"

        st.exception(e)

# -------------------------------------------------
# Result Section
# -------------------------------------------------

if st.session_state.migration_result is not None:

    result = st.session_state.migration_result

    st.divider()

    st.subheader("Migration Summary")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Tables",
        result["tables"]
    )

    c2.metric(
        "Rows",
        f"{result['rows']:,}"
    )

    c3.metric(
        "Failed Tables",
        len(result["failed_tables"])
    )

    c4.metric(
        "Time",
        f"{result['time']} sec"
    )

    st.divider()

    if result["failed_tables"]:

        st.error("Some tables failed during migration.")

        st.dataframe(
            result["failed_tables"],
            use_container_width=True
        )

    else:

        st.success(
            "✅ Migration completed successfully."
        )