import os
import subprocess
import sqlite3


API_KEY = "sk-live-abcdefgh1234567890"

def run(cmd: str):
    os.system("ls " + cmd)  # shell string -> injection risk

def run_safe(argv):
    subprocess.run(argv)

def get_user(conn, user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return conn.execute(query)

def eval_expr(expr: str):
    return eval(expr)  # dynamic execution
