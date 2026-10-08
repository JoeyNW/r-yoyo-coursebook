"""Copy a live SQLite database with the backup API."""

import argparse
import os
import sqlite3
from pathlib import Path


def backup_database(source: str, dest: str) -> None:
    """Copy a live database without reading a half-written WAL file.

    sqlite3.Connection.backup takes a consistent snapshot. Copying the
    db file directly can miss pages that are still in the WAL.
    """
    destination = Path(dest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source)
    dest_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()


def main() -> None:
    """Write one backup file. Intended for a daily scheduled task."""
    parser = argparse.ArgumentParser(description='Backup the SQLite database.')
    parser.add_argument(
        '--source',
        default=os.environ.get('DATABASE_PATH', 'data/yoyo.db'),
    )
    parser.add_argument('--dest', required=True)
    args = parser.parse_args()
    backup_database(args.source, args.dest)
    print(args.dest)


if __name__ == '__main__':
    main()
