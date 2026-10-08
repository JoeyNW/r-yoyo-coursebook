"""SQLite engine, migrations, and write transactions."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine

MIGRATIONS = Path(__file__).resolve().parent.parent / 'migrations'


def migrate(path: str) -> None:
    """Apply numbered SQL files that are newer than user_version."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        connection.isolation_level = None
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        for file in sorted(MIGRATIONS.glob('*.sql')):
            number = int(file.name.split('_', 1)[0])
            if number <= version:
                continue
            connection.executescript(file.read_text(encoding='utf-8'))
            connection.execute(f'PRAGMA user_version = {number}')
    finally:
        connection.close()


def make_engine(path: str) -> Engine:
    """Open SQLite with WAL and BEGIN IMMEDIATE transactions.

    The pysqlite driver emits its own BEGIN. Disabling that and
    starting each SQLAlchemy transaction with BEGIN IMMEDIATE keeps
    two check-ins from interleaving the balance read and the insert.
    """
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        'sqlite:///' + db_path.resolve().as_posix(),
        future=True,
        connect_args={'check_same_thread': False},
    )

    @event.listens_for(engine, 'connect')
    def _prepare(dbapi_connection, _record) -> None:
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.fetchone()
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.execute('PRAGMA synchronous=NORMAL')
        cursor.close()

    @event.listens_for(engine, 'begin')
    def _begin(conn) -> None:
        conn.exec_driver_sql('BEGIN IMMEDIATE')

    return engine


def one(conn: Connection, sql: str, params: dict | None = None):
    """Return one mapping row, or None."""
    return conn.execute(text(sql), params or {}).mappings().first()


def many(conn: Connection, sql: str, params: dict | None = None):
    """Return all mapping rows."""
    return conn.execute(text(sql), params or {}).mappings().all()


def run(conn: Connection, sql: str, params: dict | None = None):
    """Execute a statement and return the cursor result."""
    return conn.execute(text(sql), params or {})


def write_audit(
    conn: Connection,
    actor_user_id: int,
    family_id: int,
    target_type: str,
    target_id: int | None,
    action: str,
    summary: str,
    created_at: str,
) -> None:
    """Append one audit row inside the caller's transaction."""
    run(
        conn,
        '''
        INSERT INTO audit_logs (
            actor_user_id, family_id, target_type, target_id,
            action, summary, created_at
        ) VALUES (
            :actor_user_id, :family_id, :target_type, :target_id,
            :action, :summary, :created_at
        )
        ''',
        {
            'actor_user_id': actor_user_id,
            'family_id': family_id,
            'target_type': target_type,
            'target_id': target_id,
            'action': action,
            'summary': summary,
            'created_at': created_at,
        },
    )


@contextmanager
def transaction(engine: Engine) -> Iterator[Connection]:
    """Run a BEGIN IMMEDIATE transaction."""
    with engine.begin() as conn:
        yield conn
