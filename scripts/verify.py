"""Discoverable clean-checkout verification; standard library only."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
commands = [
    [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
    [sys.executable, '-m', 'agentic_eval_ops.cli', 'batch', 'examples', '--format', 'text'],
    [sys.executable, '-m', 'agentic_eval_ops.workflow_demo'],
]
for command in commands:
    subprocess.run(command, cwd=root, env=env, check=True)
