# rclone_runner.py
import subprocess
import os
from workbench_blueprint import LOG_DIR

def execute_bisync(profile, args):
    """Constructs and runs the final rclone command."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{profile}_sync.jsonl")
    
    # Enforce standard logging flags for the UI parser
    cmd = ["rclone"] + args + ["-v", "--use-json-log", "--stats", "1s"]
    
    with open(log_path, "w") as f:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        for line in process.stdout:
            f.write(line)
            f.flush()
            
    return process.returncode == 0