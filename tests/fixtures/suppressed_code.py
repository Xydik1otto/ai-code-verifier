import os


def eval_expr(expr: str):
    return eval(expr)  # aicv: ignore


def shell(cmd: str):
    os.system("ls " + cmd)  # aicv: ignore[shell_exec]


def connect(conn, user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"  # no marker -> still flagged


API_KEY = "sk-abcdefghijklmnopqrstuv"  # aicv: ignore[hardcoded_secret]
AUTH_TOKEN = "abcd1234efgh5678"  # aicv: ignore[shell_exec] -> secret rule still fires
