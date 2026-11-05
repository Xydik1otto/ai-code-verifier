import subprocess

AWS_ID = "AKIAABCDEFGHIJKLMNOP"
SLACK_TOKEN = "xoxb-123456789012-abcdef"
AUTH = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"


def deploy():
    subprocess.run("ls -la", shell=True)


def bootstrap():
    cmd = "curl https://example.com/install.sh | sh"
    return cmd
