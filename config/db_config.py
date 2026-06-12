from dotenv import load_dotenv
import os

import mysql.connector
import psycopg2

from sqlalchemy import create_engine

import logging

load_dotenv()


# Block 2 - Read Credentials from .env

#loading mysql credentials 

mysql_host = os.getenv("MYSQL_HOST")
mysql_port = os.getenv("MYSQL_PORT")
mysql_user = os.getenv("MYSQL_USER")
mysql_password = os.getenv("MYSQL_PASSWORD")
mysql_database = os.getenv("MYSQL_DATABASE")

#loading postgresql credentials

postgres_host = os.getenv("POSTGRES_HOST")
postgres_port = os.getenv("POSTGRES_PORT")
postgres_user = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_database = os.getenv("POSTGRES_DATABASE")


# Block 3 - Validate Credentials Exist
            #pass

            

#Creating sqlalchemy connection
def get_mysql_engine():
    try:
        mysql_database_url = f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
        engine = create_engine(mysql_database_url , echo = True)
        print("Succesfully connected mysql using alchemy")
        return engine
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return None


#Vai alchemy
def get_mysql_connection():
    try:
        connection = mysql.connector.connect(
            host = mysql_host,
            port = int(mysql_port),
            user = mysql_user,
            password = mysql_password,
            database = mysql_database
        )
        logging.info("Succesfully connected mysql using mysql connector")
        return connection
    except mysql.connector.Error as e:
        logging.error(f"ERROR: {str(e)}")
        raise 

def get_postgres_connection():
    try:
        connection = psycopg2.connect(
            host = postgres_host,
            port = int(postgres_port),
            user = postgres_user,
            password = postgres_password,
            dbname = postgres_database
        )
        logging.info("Succesfully connected postgres using psycopg2")
        return connection
    except psycopg2.Error as e:
        logging.error(f"ERROR: {str(e)}")
        raise 


def get_mysql_engine():
    try:
        Database_url = (
            f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
        )
        engine = create_engine(Database_url,pool_pre_ping=True)
        logging.info("Succesfully connected mysql using alchemy")
        return engine
    except Exception as e:
        logging.error(f"My SQL Connection Fails : {e}")
        raise

def get_postgres_engine():
    try:
        Database_url = (
            f"postgresql+psycopg2://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_database}"
        )
        engine = create_engine(Database_url,pool_pre_ping=True,pool_size=5)
        logging.info("Postgres connected using alchemy")
        return engine
    except Exception as e:
        logging.error(f"Postgre Connection Fails : {e}")
        raise

def test_all_connection():
    """
        Call this once to verify all 4 connections work.
        Run: python -c "from config.db_config import test_all_connections; test_all_connections()
    """
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    print(f"Mysql Version  {cursor.fetchone()[0]}")

    #Testing postgresql connection
    
    conn = get_postgres_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    print(f"Postgres Version - {cursor.fetchone()[0]}")

    #Testing mysql alchemy connection

    engine = get_mysql_engine()
    with engine.connect() as c:
        print( "Sql alchemy connected")
    engine.dispose()

    #Testing postgres alchemy connection

    engine = get_postgres_engine()
    with engine.connect() as c:
        print("Postgre alchemy connected")
    engine.dispose()

    print("All connections verified successfully")



test_all_connection()