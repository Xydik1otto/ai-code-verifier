import sqlite3


def get_user(conn: sqlite3.Connection, user_id: int):
    query = "SELECT * FROM users WHERE id = ?"
    return conn.execute(query, (user_id,))


def run_safe(argv: list):
    import subprocess
    return subprocess.run(argv, check=False)
