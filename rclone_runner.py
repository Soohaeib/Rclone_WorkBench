import subprocess
import os
import signal
import workbench_blueprint

def run_sync_session(profile: str, args: list):
    """Executes rclone, forces JSON/INFO logging, and writes to log file in real-time."""
    os.makedirs(workbench_blueprint.LOG_DIR, exist_ok=True)
    log_path = os.path.join(workbench_blueprint.LOG_DIR, f"{profile}_sync.jsonl")
    
    # Enforce required flags for the log_formatter to work properly
    cmd = ["rclone"] + args + ["-v", "--use-json-log", "--stats", "1s", "--stats-one-line"]
    
    # Clear previous log session
    with open(log_path, "w", encoding="utf-8") as f: 
        f.write("")
    
    # Launch detached process
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        bufsize=1, # Line buffered
        universal_newlines=True, 
        preexec_fn=os.setsid
    )
    
    output_buffer = []
    
    # Safe loop to capture stdout in real-time and stream it to the JSONL file
    with open(log_path, "a", encoding="utf-8") as f:
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                output_buffer.append(line)
                f.write(line)
                f.flush() # Force write to disk immediately so tailer catches it
                
    return {
        "success": process.returncode == 0,
        "process": process,
        "output": "".join(output_buffer)
    }

def kill_process(process):
    """Safely kills the entire process group to ensure child processes die."""
    if process and process.poll() is None:
        try: 
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError: 
            pass