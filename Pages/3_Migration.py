import time

# pyrefly: ignore [missing-import]
import streamlit as st

from streamlit_utils.migration_runner import run_migration


st.set_page_config(
    page_title="Migration",
    page_icon="🔄",
    layout="wide",
)
def initialize_state():
    defaults = {
        "migration_result": None,
        "migration_running": False,
        "migration_progress": 0,
        "migration_status": "Waiting to start...",
        "current_table": "-",
        "elapsed_time": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()

st.title("🔄 MySQL ➜ PostgreSQL Migration")
st.markdown(
    """
This page performs the complete migration process.

### Migration Steps

1. Analyze Schema
2. Extract Data
3. Transform Data
4. Load Data
5. Add Foreign Keys
"""
)

st.divider()
st.subheader("Migration Progress")

# Create each live UI element exactly once.  The callbacks below update these
# existing elements instead of adding a second progress bar or status section.
progress_bar = st.progress(st.session_state.migration_progress)
progress_col, time_col, status_col = st.columns(3)
progress_metric = progress_col.empty()
time_metric = time_col.empty()
status_metric = status_col.empty()
stage_box = st.empty()
table_box = st.empty()

progress_metric.metric("Progress", f"{st.session_state.migration_progress}%")
time_metric.metric("Elapsed Time", f"{st.session_state.elapsed_time} sec")
status_metric.metric(
    "Status",
    "Running" if st.session_state.migration_running else "Idle",
)
stage_box.info(f"Current Stage: {st.session_state.migration_status}")
table_box.info(f"Current Table: {st.session_state.current_table}")

st.divider()

start_migration = st.button(
    "▶ Start Migration",
    type="primary",
    use_container_width=True,
    disabled=st.session_state.migration_running,
)

if start_migration:
    st.session_state.migration_running = True
    st.session_state.migration_result = None
    st.session_state.migration_progress = 0
    st.session_state.migration_status = "Initializing..."
    st.session_state.current_table = "-"
    st.session_state.elapsed_time = 0

    start_time = time.time()
    progress_bar.progress(0)
    progress_metric.metric("Progress", "0%")
    time_metric.metric("Elapsed Time", "0 sec")
    status_metric.metric("Status", "Running")
    stage_box.info("Current Stage: Initializing...")
    table_box.info("Current Table: -")

    # Start each migration with a fresh log.  Keeping this here prevents a
    # normal Streamlit rerun from erasing logs after the migration finishes.
    with open("logs/migration.log", "w", encoding="utf-8"):
        pass

    def update_progress(percent):
        elapsed = int(time.time() - start_time)
        st.session_state.migration_progress = percent
        st.session_state.elapsed_time = elapsed
        progress_bar.progress(percent)
        progress_metric.metric("Progress", f"{percent}%")
        time_metric.metric("Elapsed Time", f"{elapsed} sec")
        status_metric.metric("Status", "Running")

    def update_status(message):
        st.session_state.migration_status = message
        stage_box.info(f"Current Stage: {message}")

    def update_table(table):
        st.session_state.current_table = table
        table_box.info(f"Current Table: {table}")

    try:
        result = run_migration(
            progress_callback=update_progress,
            status_callback=update_status,
            table_callback=update_table,
        )
    except Exception as error:
        st.session_state.migration_running = False
        st.session_state.migration_status = "Migration Failed"
        status_metric.metric("Status", "Failed")
        stage_box.error("Current Stage: Migration Failed")
        st.exception(error)
    else:
        st.session_state.migration_result = result
        st.session_state.migration_running = False
        st.session_state.migration_progress = 100
        st.session_state.migration_status = "Migration Completed"
        progress_bar.progress(100)
        progress_metric.metric("Progress", "100%")
        status_metric.metric("Status", "Completed")
        stage_box.success("Current Stage: Migration Completed")
        st.rerun()


if st.session_state.migration_result is not None:
    result = st.session_state.migration_result

    st.divider()
    st.subheader("Migration Summary")
    tables_col, rows_col, failed_col, duration_col = st.columns(4)
    tables_col.metric("Tables", result["tables"])
    rows_col.metric("Rows", f"{result['rows']:,}")
    failed_col.metric("Failed Tables", len(result["failed_tables"]))
    duration_col.metric("Time", f"{result['time']} sec")

    if result["failed_tables"]:
        st.error("Some tables failed during migration.")
        st.dataframe(result["failed_tables"], use_container_width=True)