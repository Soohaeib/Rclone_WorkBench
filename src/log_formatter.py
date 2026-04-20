import os, json, time, datetime, threading, re
from src.workbench_blueprint import LOG_DIR

# Standard Rclone ANSI escape sequences to clean terminal colors
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
_active_tails = {}

def format_line(line: str):
    """Parses raw JSONL string into UI-friendly actions."""
    stripped = line.strip()
    if not stripped: return []

    try:
        data = json.loads(stripped)
        if "stats" in data or "transferred" in data: 
            return [("stats", data)]
        
        msg = ANSI_ESCAPE.sub('', data.get("msg", "")).strip()
        if not msg: return []

        obj = data.get("object", "")
        if obj and obj not in msg: msg = f"{msg}: {obj}"
        
        level = str(data.get("level", "INFO")).upper()
        return [("log", f"[{level}] {msg}\n")]
        
    except json.JSONDecodeError:
        clean = ANSI_ESCAPE.sub('', stripped).strip()
        if not clean: return []
        if " / " in clean and ("ETA" in clean or "%" in clean): 
            return [("stats", {"msg": clean})]
        return [("log", clean + "\n")]

def start_live_feed(profile: str, ui_callback):
    """Tails the log file and streams updates to the UI safely."""
    stop_event = threading.Event()
    _active_tails[profile] = stop_event

    def _tailer():
        path = os.path.join(LOG_DIR, f"{profile}_sync.jsonl")
        last_pos = 0
        while not stop_event.is_set():
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        f.seek(last_pos)
                        lines = f.readlines()
                        last_pos = f.tell()
                        
                        actions = []
                        for line in lines: 
                            actions.extend(format_line(line))
                        if actions: 
                            ui_callback(actions)
                except Exception: 
                    pass
            time.sleep(0.3)

    # Run as a daemon thread so it dies when the app closes
    threading.Thread(target=_tailer, daemon=True).start()

def stop_live_feed(profile: str):
    """Stops the tailer thread for a specific profile."""
    if profile in _active_tails:
        _active_tails[profile].set()

def get_last_run_time(profile: str) -> str:
    """Parses the raw ISO timestamp from the end of the profile's log file."""
    path = os.path.join(LOG_DIR, f"{profile}_sync.jsonl")
    if not os.path.exists(path): 
        return "Never"
    
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            lines = f.read().decode('utf-8', errors='ignore').splitlines()
            
        for line in reversed(lines):
            if not line.strip(): continue
            try:
                data = json.loads(line)
                if "time" in data:
                    return data["time"] # Return raw string: "2026-04-18T19:09:46..."
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
        
    return "Never"