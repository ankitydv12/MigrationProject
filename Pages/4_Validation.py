import streamlit as st
import pandas as pd
import os

from validation.Validate import (
    get_mysql_row_counts,
    get_postgres_row_count,
    validate_row_counts,
    generate_report
)

st.set_page_config(
    page_title="Validation",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Migration Validation")

st.write("Compare MySQL and PostgreSQL row counts.")

st.divider()

if st.button("Run Validation", type="primary"):

    with st.spinner("Running Validation..."):

        mysql_counts = get_mysql_row_counts()

        postgres_counts = get_postgres_row_count(
            list(mysql_counts.keys())
        )

        results = validate_row_counts(
            mysql_counts,
            postgres_counts
        )

        success = generate_report(results)

        df = pd.DataFrame(results)

    st.success("Validation Completed")

    st.divider()

    total = len(df)

    passed = len(df[df["status"] == "PASS"])

    failed = len(df[df["status"] == "FAIL"])

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Tables", total)

    col2.metric("Passed", passed)

    col3.metric("Failed", failed)

    st.divider()

    st.subheader("Validation Result")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    if failed == 0:

        st.success("All tables validated successfully.")

    else:

        st.error(f"{failed} tables failed validation.")

    report_path = os.path.join(
        "reports",
        "validation_report.csv"
    )

    if os.path.exists(report_path):

        with open(report_path, "rb") as file:

            st.download_button(
                label="Download Validation Report",
                data=file,
                file_name="validation_report.csv",
                mime="text/csv"
            )