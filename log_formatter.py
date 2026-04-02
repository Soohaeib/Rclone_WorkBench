import json
import re

# Standard Rclone ANSI escape sequences
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def format_line(line: str):
    """
    Translates a single JSONL line into a list of (action_type, data) tuples.
    Actions: 'log' (message string), 'stats' (progress dict), 'error' (critical)
    """
    line = line.strip()
    if not line: return []

    try:
        data = json.loads(line)
        
        # Handle Rclone Stats objects
        if "stats" in data or "transferred" in data:
            return [("stats", data)]
        
        # Clean the message
        msg = ANSI_ESCAPE.sub('', data.get("msg", "")).strip()
        if not msg: return []

        level = str(data.get("level", "info")).upper()
        obj = data.get("object", "")
        formatted_msg = f"[{level}] {f'{obj}: ' if obj else ''}{msg}\n"
        
        return [("log", formatted_msg)]

    except json.JSONDecodeError:
        # Fallback for non-JSON lines (e.g. startup errors)
        clean = ANSI_ESCAPE.sub('', line).strip()
        if not clean: return []
        return [("log", f"{clean}\n")]