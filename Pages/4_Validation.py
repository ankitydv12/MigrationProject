import streamlit as st
import pandas as pd
import os

from validation.Validate import run_validation

st.set_page_config(
    page_title="Validation",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Migration Validation")

st.write("Compare MySQL and PostgreSQL row counts, key counts, sequence positions, and sample data values.")

st.divider()

if st.button("Run Validation", type="primary"):
    with st.spinner("Running Validation..."):
        success = run_validation()
        if success:
            st.success("Validation Completed Successfully - All Checks Passed!")
        else:
            st.error("Validation Completed with Failures. Check the details below.")

st.divider()

report_path = os.path.join("reports", "validation_report.csv")

if os.path.exists(report_path):
    try:
        df = pd.read_csv(report_path)
        total = len(df)
        passed = len(df[df["status"] == "PASS"])
        failed = len(df[df["status"] == "FAIL"])

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Tables Checked", total)
        col2.metric("Passed", passed)
        col3.metric("Failed", failed)

        st.divider()

        st.subheader("Validation Result Details")
        st.dataframe(
            df,
            width='stretch',
            hide_index=True
        )

        with open(report_path, "rb") as file:
            st.download_button(
                label="Download Validation Report",
                data=file,
                file_name="validation_report.csv",
                mime="text/csv"
            )
    except Exception as e:
        st.error(f"Error reading validation report: {e}")
else:
    st.info("No validation report found. Please click 'Run Validation' to execute data integrity checks.")