import streamlit as st
import os
import time

st.set_page_config(
    page_title="Migration Logs",
    page_icon="📄",
    layout="wide"
)

st.title("📄 Migration Logs")

LOG_FILE = "logs/migration.log"

st.write("View migration logs generated during execution.")

st.divider()

# -----------------------------
# Auto Refresh Option
# -----------------------------

auto_refresh = st.checkbox("Auto Refresh", value=False)

# -----------------------------
# Search Option
# -----------------------------

search_text = st.text_input("Search Log")

# -----------------------------
# Log Level Filter
# -----------------------------
col1, col2 = st.columns([4, 1])
with col1:

    level = st.selectbox(
    "Filter",
    [
        "ALL",
        "INFO",
        "WARNING",
        "ERROR"
    ]
)
with col2:

    if st.button(
        "🗑 Clear Logs",
        use_container_width=True
    ):

        open(LOG_FILE, "w").close()

        st.success("Logs cleared successfully.")

        st.rerun()

st.divider()

# -----------------------------
# Read Log File
# -----------------------------

if os.path.exists(LOG_FILE):

    try:

       with open(LOG_FILE, "r", encoding="utf-8") as file:
        logs = file.readlines()
        st.caption(f"Total Log Entries : {len(logs)}")

    except Exception:

       logs = []

    # Apply Filter
    if level != "ALL":
        logs = [
            line for line in logs
            if level in line
        ]

    # Apply Search
    if search_text:
        logs = [
            line for line in logs
            if search_text.lower() in line.lower()
        ]

    st.text_area(
        "Log Output",
        "".join(logs),
        height=500
    )

    # Download Button
    with open(LOG_FILE, "rb") as file:

        st.download_button(
            "⬇ Download Log File",
            data=file,
            file_name="migration.log"
        )

else:

    st.info("No logs available.")

# -----------------------------
# Auto Refresh
# -----------------------------

if auto_refresh:

    time.sleep(2)

    st.rerun()