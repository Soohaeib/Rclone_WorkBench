import subprocess, os, signal, json, datetime, threading
from src.workbench_blueprint import LOG_DIR

def run_sync_session(profile: str, args: list, proc_callback=None):
    """Executes rclone, forces JSON/INFO logging, and appends to log file in real-time."""
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{profile}_sync.jsonl")
    
    cmd = ["rclone"] + args + ["-v", "--use-json-log", "--stats", "1s", "--stats-one-line"]
    
    with open(log_path, "a", encoding="utf-8") as f:
        timestamp = datetime.datetime.now().isoformat()
        divider = json.dumps({"time": timestamp, "level": "info", "msg": f"━━━━━━━━━━━ [{timestamp}] ━━━━━━━━━━━"})
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

    # NEW: Instantly pass the running process back to the app so we can kill it if needed!
    if proc_callback:
        proc_callback(process)

    # --- NON-BLOCKING LOG CAPTURE ---
    def _log_capture_thread(proc, log_file_path):
        with open(log_file_path, "a", encoding="utf-8") as lf:
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if not line and proc.poll() is not None:
                    break
                if line:
                    lf.write(line)
                    lf.flush()
    
    log_thread = threading.Thread(target=_log_capture_thread, args=(process, log_path), daemon=True)
    log_thread.start()
    
    process.wait()

    return {
        "success": process.returncode == 0,
        "process": process,
        "output": "" 
    }

def kill_process(process, force=False):
    """Sends a signal to the process group: SIGINT for graceful, SIGKILL for forceful."""
    if process and process.poll() is None:
        # Choose the signal based on the 'force' flag
        target_signal = signal.SIGKILL if force else signal.SIGINT
        
        try: 
            os.killpg(os.getpgid(process.pid), target_signal)
        except Exception as e:
            # It's good practice to at least print the error if killing fails
            print(f"Failed to kill process {process.pid} with signal {target_signal}: {e}")
            pass