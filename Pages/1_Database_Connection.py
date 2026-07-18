import streamlit as st
import mysql.connector
import psycopg2

st.set_page_config(
    page_title="Database Connection",
    page_icon="🔗",
    layout="wide"
)

st.title("🔗 Database Connection")

st.header("MySQL")

mysql_host = st.text_input("Host", "localhost", key="mysql_host")
mysql_port = st.number_input("Port", value=3306, key="mysql_port")
mysql_database = st.text_input("Database", key="mysql_db")
mysql_user = st.text_input("Username", key="mysql_user")
mysql_password = st.text_input(
    "Password",
    type="password",
    key="mysql_password"
)

st.divider()

st.header("PostgreSQL")

pg_host = st.text_input("Host", "localhost", key="pg_host")
pg_port = st.number_input("Port", value=5432, key="pg_port")
pg_database = st.text_input("Database", key="pg_db")
pg_user = st.text_input("Username", key="pg_user")
pg_password = st.text_input(
    "Password",
    type="password",
    key="pg_password"
)

st.divider()

if st.button("Test Connections", use_container_width=True):

    mysql_ok = False
    pg_ok = False

    # MySQL
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            database=mysql_database
        )
        conn.close()

        mysql_ok = True

        st.success("✅ MySQL Connected")

    except Exception as e:
        st.error(f"MySQL Error\n{e}")

    # PostgreSQL
    try:

        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            user=pg_user,
            password=pg_password,
            dbname=pg_database
        )

        conn.close()

        pg_ok = True

        st.success("✅ PostgreSQL Connected")

    except Exception as e:

        st.error(f"PostgreSQL Error\n{e}")

    if mysql_ok and pg_ok:

        st.session_state["mysql"] = {
            "host": mysql_host,
            "port": mysql_port,
            "database": mysql_database,
            "user": mysql_user,
            "password": mysql_password
        }

        st.session_state["postgres"] = {
            "host": pg_host,
            "port": pg_port,
            "database": pg_database,
            "user": pg_user,
            "password": pg_password
        }

        st.success("Credentials saved for this session.")