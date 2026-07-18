from dotenv import load_dotenv
import os
import mysql.connector
import psycopg2
from sqlalchemy import create_engine
import logging
import psycopg2.pool
import mysql.connector.pooling
import threading
import config

load_dotenv()

# Logger initialization
logging.basicConfig(
    level=logging.INFO,
    format="        Logger :%(name)s - %(asctime)s -%(levelname)s -%(message)s"
)

logger = logging.getLogger(__name__)

# Read credentials from .env
mysql_host = os.getenv("MYSQL_HOST")
mysql_port = os.getenv("MYSQL_PORT")
mysql_user = os.getenv("MYSQL_USER")
mysql_password = os.getenv("MYSQL_PASSWORD")
mysql_database = os.getenv("MYSQL_DATABASE")

postgres_host = os.getenv("POSTGRES_HOST")
postgres_port = os.getenv("POSTGRES_PORT")
postgres_user = os.getenv("POSTGRES_USER")
postgres_password = os.getenv("POSTGRES_PASSWORD")
postgres_database = os.getenv("POSTGRES_DATABASE")

# Validate credentials exist
REQUIRED_VARS = [
    "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER",
    "MYSQL_PASSWORD", "MYSQL_DATABASE",
    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER",
    "POSTGRES_PASSWORD", "POSTGRES_DATABASE"
]

missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing:
    logger.warning(
        f"Missing environment variables: {missing}. Check your .env file."
    )

# Connection pools globals
postgres_pool = None
mysql_pool = None

class PooledPostgresConnection:
    def __init__(self, pool, raw_conn):
        self._pool = pool
        self._raw_conn = raw_conn

    def __getattr__(self, name):
        return getattr(self._raw_conn, name)

    def close(self):
        self._pool.put_connection(self._raw_conn)

class PooledMySQLConnection:
    def __init__(self, pool, raw_conn):
        self._pool = pool
        self._raw_conn = raw_conn

    def __getattr__(self, name):
        return getattr(self._raw_conn, name)

    def close(self):
        self._pool.put_connection(self._raw_conn)

class PGPool:
    def __init__(self, pool_size):
        self.pool_size = pool_size
        self.pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=pool_size,
            host=postgres_host,
            port=int(postgres_port),
            user=postgres_user,
            password=postgres_password,
            dbname=postgres_database
        )
        self.reused_count = 0
        self.recreated_count = 0
        self._lock = threading.Lock()
        logger.info("Pool Initialized")

    def get_connection(self):
        with self._lock:
            try:
                conn = self.pool.getconn()
                is_invalid = False
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.close()
                except Exception:
                    is_invalid = True
                
                if is_invalid:
                    self.pool.putconn(conn, close=True)
                    conn = self.pool.getconn()
                    self.recreated_count += 1
                    logger.info("Connection Recreated")
                else:
                    self.reused_count += 1
                
                logger.info("Connection Acquired")
                return PooledPostgresConnection(self, conn)
            except Exception as e:
                logger.error(f"Failed to get PG connection from pool: {e}")
                conn = psycopg2.connect(
                    host=postgres_host,
                    port=int(postgres_port),
                    user=postgres_user,
                    password=postgres_password,
                    dbname=postgres_database
                )
                self.recreated_count += 1
                logger.info("Connection Recreated")
                return PooledPostgresConnection(self, conn)

    def put_connection(self, conn):
        with self._lock:
            try:
                self.pool.putconn(conn)
                logger.info("Connection Returned")
            except Exception as e:
                logger.error(f"Error returning PG connection: {e}")

    def recreate_postgres_connection(self, proxy_conn):
        with self._lock:
            try:
                raw_conn = proxy_conn._raw_conn
                self.pool.putconn(raw_conn, close=True)
            except Exception:
                pass
            
            new_raw_conn = self.pool.getconn()
            self.recreated_count += 1
            logger.info("Connection Recreated")
            proxy_conn._raw_conn = new_raw_conn
            return proxy_conn

    def close_all(self):
        with self._lock:
            try:
                self.pool.closeall()
            except Exception:
                pass

class MySQLPool:
    def __init__(self, pool_size):
        self.pool_size = pool_size
        Database_url = (
            f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
        )
        self.engine = create_engine(
            Database_url,
            pool_size=pool_size,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args={"use_pure": True}
        )
        self.reused_count = 0
        self.recreated_count = 0
        self._lock = threading.Lock()
        logger.info("Pool Initialized")

    def get_connection(self):
        with self._lock:
            try:
                conn = self.engine.connect()
                self.reused_count += 1
                logger.info("Connection Acquired")
                return PooledMySQLConnection(self, conn)
            except Exception as e:
                self.recreated_count += 1
                logger.info("Connection Recreated")
                raise

    def put_connection(self, conn):
        with self._lock:
            try:
                conn.close()
                logger.info("Connection Returned")
            except Exception as e:
                logger.error(f"Error returning MySQL connection: {e}")

    def close_all(self):
        with self._lock:
            try:
                self.engine.dispose()
            except Exception:
                pass

def init_pools(pool_size):
    global postgres_pool, mysql_pool
    if getattr(config, "USE_CONNECTION_POOL", True):
        if postgres_pool is None:
            postgres_pool = PGPool(pool_size)
        if mysql_pool is None:
            mysql_pool = MySQLPool(pool_size)

def dispose_pools():
    global postgres_pool, mysql_pool
    if postgres_pool is not None:
        postgres_pool.close_all()
        postgres_pool = None
    if mysql_pool is not None:
        mysql_pool.close_all()
        mysql_pool = None

# DB connection wrappers that transparently use pools if available
def get_mysql_connection():
    if getattr(config, "USE_CONNECTION_POOL", True) and mysql_pool is not None:
        return mysql_pool.get_connection()
    try:
        connection = mysql.connector.connect(
            host=mysql_host,
            port=int(mysql_port),
            user=mysql_user,
            password=mysql_password,
            database=mysql_database
        )
        logging.info("Succesfully connected mysql using mysql connector")
        return connection
    except mysql.connector.Error as e:
        logging.error(f"ERROR: {str(e)}")
        raise 

def get_postgres_connection():
    if getattr(config, "USE_CONNECTION_POOL", True) and postgres_pool is not None:
        return postgres_pool.get_connection()
    try:
        connection = psycopg2.connect(
            host=postgres_host,
            port=int(postgres_port),
            user=postgres_user,
            password=postgres_password,
            dbname=postgres_database
        )
        logging.info("Succesfully connected postgres using psycopg2")
        return connection
    except psycopg2.Error as e:
        logging.error(f"ERROR: {str(e)}")
        raise 

def get_mysql_engine():
    if getattr(config, "USE_CONNECTION_POOL", True) and mysql_pool is not None:
        return mysql_pool.engine
    try:
        Database_url = (
            f"mysql+mysqlconnector://{mysql_user}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_database}"
        )
        engine = create_engine(Database_url, pool_pre_ping=True, connect_args={"use_pure": True})
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
        engine = create_engine(Database_url, pool_pre_ping=True, pool_size=5)
        logging.info("Postgres connected using alchemy")
        return engine
    except Exception as e:
        logging.error(f"Postgre Connection Fails : {e}")
        raise

def test_all_connection():
    conn = get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    print(f"Mysql Version  {cursor.fetchone()[0]}")
    conn.close()

    conn = get_postgres_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION()")
    print(f"Postgres Version - {cursor.fetchone()[0]}")
    conn.close()

    engine = get_mysql_engine()
    with engine.connect() as c:
        print("Sql alchemy connected")
    if mysql_pool is None:
        engine.dispose()

    engine = get_postgres_engine()
    with engine.connect() as c:
        print("Postgre alchemy connected")
    engine.dispose()

    print("All connections verified successfully")

def update_db_credentials(mysql_creds, pg_creds):
    global mysql_host, mysql_port, mysql_user, mysql_password, mysql_database
    global postgres_host, postgres_port, postgres_user, postgres_password, postgres_database
    
    # 1. Dispose existing pools
    dispose_pools()
    
    # 2. Update globals
    mysql_host = mysql_creds.get("host", mysql_host)
    mysql_port = str(mysql_creds.get("port", mysql_port))
    mysql_user = mysql_creds.get("user", mysql_user)
    mysql_password = mysql_creds.get("password", mysql_password)
    mysql_database = mysql_creds.get("database", mysql_database)
    
    postgres_host = pg_creds.get("host", postgres_host)
    postgres_port = str(pg_creds.get("port", postgres_port))
    postgres_user = pg_creds.get("user", postgres_user)
    postgres_password = pg_creds.get("password", postgres_password)
    postgres_database = pg_creds.get("database", postgres_database)
    
    # 3. Update os.environ
    os.environ["MYSQL_HOST"] = mysql_host
    os.environ["MYSQL_PORT"] = mysql_port
    os.environ["MYSQL_USER"] = mysql_user
    os.environ["MYSQL_PASSWORD"] = mysql_password
    os.environ["MYSQL_DATABASE"] = mysql_database
    
    os.environ["POSTGRES_HOST"] = postgres_host
    os.environ["POSTGRES_PORT"] = postgres_port
    os.environ["POSTGRES_USER"] = postgres_user
    os.environ["POSTGRES_PASSWORD"] = postgres_password
    os.environ["POSTGRES_DATABASE"] = postgres_database
    
    # 4. Write to .env file to persist
    try:
        with open(".env", "w", encoding="utf-8") as f:
            f.write(f"MYSQL_HOST={mysql_host}\n")
            f.write(f"MYSQL_PORT={mysql_port}\n")
            f.write(f"MYSQL_USER={mysql_user}\n")
            f.write(f"MYSQL_PASSWORD={mysql_password}\n")
            f.write(f"MYSQL_DATABASE={mysql_database}\n\n")
            f.write(f"POSTGRES_HOST={postgres_host}\n")
            f.write(f"POSTGRES_PORT={postgres_port}\n")
            f.write(f"POSTGRES_USER={postgres_user}\n")
            f.write(f"POSTGRES_PASSWORD={postgres_password}\n")
            f.write(f"POSTGRES_DATABASE={postgres_database}\n")
        logger.info("Credentials written to .env successfully")
    except Exception as e:
        logger.error(f"Failed to save credentials to .env: {e}")

if __name__ == "__main__":
    test_all_connection()
