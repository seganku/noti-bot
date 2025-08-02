"""
Module: bot/database.py

Handles SQLite database connectivity, schema initialization, and query execution for notifications.
"""
import sqlite3
from datetime import datetime, UTC
from utils import log_message

class Database:
    """
    Database wrapper for SQLite with automatic connection handling and schema setup.
    """
    def __init__(self):
        """
        Initialize the Database instance and establish the first connection.
        """
        self.conn = None
        self.cursor = None
        self.connect()

    def connect(self):
        """
        Establish a connection to the SQLite database 'noti.db', set up row parser,
        and initialize the schema if necessary.

        Reconnects if there was a previous connection. Registers a converter
        for UTC timestamps.
        """
        try:
            if self.conn:
                try:
                    self.conn.close()
                except Exception as e:
                    log_message(f"Error closing existing DB connection: {e}", "warning")

            def parse_utc_timestamp(ts):
                """
                Parse a byte-string timestamp from SQLite into a Python datetime with UTC tz.
                """
                try:
                    return datetime.fromisoformat(ts.decode()).replace(tzinfo=UTC)
                except Exception as e:
                    log_message(f"Error parsing UTC timestamp: {e}", "error")
                    return datetime.now(UTC)

            sqlite3.register_converter("timestamp", parse_utc_timestamp)

            self.conn = sqlite3.connect(
                'noti.db',
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                check_same_thread=False
            )
            self.cursor = self.conn.cursor()
            self._initialize_db()

        except Exception as e:
            log_message(f"Database connection error: {e}", "error")

    def _initialize_db(self):
        """
        Create the 'noti' table and necessary indexes if they do not exist.
        """
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS noti (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_repeating BOOLEAN DEFAULT FALSE,
                    interval_value INTEGER,
                    interval_unit TEXT,
                    end_time TIMESTAMP,
                    last_triggered TIMESTAMP,
                    max_occurrences INTEGER,
                    complete BOOLEAN NOT NULL DEFAULT 0
                )
            ''')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_guild ON noti (guild_id)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON noti (start_time)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_repeating ON noti (is_repeating)')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_complete ON noti (complete)')
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS id_cache (
                    id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL DEFAULT 0,
                    obj_type TEXT    NOT NULL,
                    name TEXT        NOT NULL,
                    last_updated TIMESTAMP NOT NULL,
                    PRIMARY KEY(id, guild_id, obj_type)
                )
            ''')
            self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_id_cache_id ON id_cache (id)')
            self.conn.commit()
        except Exception as e:
            log_message(f"Error initializing database schema: {e}", "error")

    def ensure_connection(self):
        """
        Verify that the current connection is alive by executing a simple query.
        If it fails, reconnect and reinitialize the schema.
        """
        try:
            self.cursor.execute('SELECT 1')
        except (sqlite3.ProgrammingError, sqlite3.InterfaceError, sqlite3.OperationalError) as e:
            log_message(f"Lost DB connection, reconnecting: {e}", "warning")
            self.connect()

    def execute(self, query, params=()):
        """
        Execute a modifying SQL query (INSERT/UPDATE/DELETE) with parameters,
        ensuring the connection is alive and committing after success.

        Returns the SQLite cursor for further inspection.
        """
        try:
            self.ensure_connection()
            result = self.cursor.execute(query, params)
            self.conn.commit()
            return result
        except Exception as e:
            log_message(f"Error executing query: {e}\nQuery: {query}\nParams: {params}", "error")
            raise

    def fetchall(self, query, params=()):
        """
        Execute a SELECT query with parameters and return all fetched rows.

        Ensures the connection is alive before querying.
        """
        try:
            self.ensure_connection()
            return self.cursor.execute(query, params).fetchall()
        except Exception as e:
            log_message(f"Error fetching data: {e}\nQuery: {query}\nParams: {params}", "error")
            raise

