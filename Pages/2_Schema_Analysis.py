import streamlit as st
import pandas as pd

from utils.schema_analyzer import analyze_schema

st.set_page_config(
    page_title="Schema Analysis",
    page_icon="🗂️",
    layout="wide"
)

st.title("🗂️ Schema Analysis")

schema = analyze_schema()

# -----------------------------
# Migration Order
# -----------------------------

st.header("Migration Order")

migration_df = pd.DataFrame({
    "Order": range(1, len(schema["migration_order"]) + 1),
    "Table Name": schema["migration_order"]
})

st.dataframe(
    migration_df,
    width='stretch',
    hide_index=True
)

# -----------------------------
# Foreign Keys
# -----------------------------

st.header("Foreign Key Relationships")

fk_df = pd.DataFrame(
    schema["foreign_keys"],
    columns=[
        "Child Table",
        "Child Column",
        "Parent Table",
        "Parent Column"
    ]
)

st.dataframe(
    fk_df,
    width='stretch',
    hide_index=True
)

# -----------------------------
# UUID Tables
# -----------------------------

st.header("UUID Tables")

uuid_df = pd.DataFrame(
    schema["uuid_tables"],
    columns=["Table Name"]
)

st.dataframe(
    uuid_df,
    width='stretch',
    hide_index=True
)

# -----------------------------
# JSON Columns
# -----------------------------

st.header("JSON Columns")

json_rows = []

for table, cols in schema["json_columns"].items():
    for col in cols:
        json_rows.append({
            "Table": table,
            "Column": col
        })

json_df = pd.DataFrame(json_rows)

st.dataframe(
    json_df,
    width='stretch',
    hide_index=True
)

# -----------------------------
# Boolean Columns
# -----------------------------

st.header("Boolean Columns")

bool_rows = []

for table, cols in schema["boolean_columns"].items():
    for col in cols:
        bool_rows.append({
            "Table": table,
            "Column": col
        })

bool_df = pd.DataFrame(bool_rows)

st.dataframe(
    bool_df,
    width='stretch',
    hide_index=True
)