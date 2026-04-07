import subprocess, os, signal, json, datetime
import src.workbench_blueprint as blueprint

def run_sync_session(profile: str, args: list):
    """Executes rclone, forces JSON/INFO logging, and appends to log file in real-time."""
    os.makedirs(blueprint.LOG_DIR, exist_ok=True)
    log_path = os.path.join(blueprint.LOG_DIR, f"{profile}_sync.jsonl")
    
    cmd = ["rclone"] + args + ["-v", "--use-json-log", "--stats", "1s", "--stats-one-line"]
    
    # Append a session divider instead of clearing the log
    with open(log_path, "a", encoding="utf-8") as f:
        timestamp = datetime.datetime.now().isoformat()
        divider = json.dumps({"time": timestamp, "level": "info", "msg": "━━━━━━━━━━━ NEW SYNC SESSION ━━━━━━━━━━━"})
        f.write(divider + "\n")
    
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True, 
        bufsize=1, 
        universal_newlines=True, 
        preexec_fn=os.setsid
    )
    
    output_buffer = []
    
    with open(log_path, "a", encoding="utf-8") as f:
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                output_buffer.append(line)
                f.write(line)
                f.flush() 
                
    return {
        "success": process.returncode == 0,
        "process": process,
        "output": "".join(output_buffer)
    }

def kill_process(process):
    if process and process.poll() is None:
        try: os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except: pass