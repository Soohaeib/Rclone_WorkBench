import os
from dataclasses import dataclass, field
from typing import List, Dict, Union, Any

# This automatically figures out where the app is installed
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import subprocess
try:
    _res = subprocess.run(['rclone', 'config', 'file'], capture_output=True, text=True)
    RCLONE_CONF_PATH = _res.stdout.splitlines()[1].strip() if _res.returncode == 0 else os.path.expanduser('~/.config/rclone/rclone.conf')
except:
    RCLONE_CONF_PATH = os.path.expanduser('~/.config/rclone/rclone.conf')
RCLONE_CACHE_DIR = os.path.expanduser('~/.cache/rclone/bisync')
JSON_CONFIG_FILE = os.path.join(APP_DIR, 'bisync_settings.json')
LOG_DIR = os.path.join(APP_DIR, 'logs')

TRASH_LOCAL_NAME = '.rclone_trash_local'
TRASH_CLOUD_NAME = '.rclone_trash_cloud'

@dataclass
class SmartPreset:
    label: str; id: str; desc: str; color: str = "#ecf0f1"
    trigger_condition: str = "manual"; lifecycle: str = "persistent"
    auto_apply: bool = False; python_hook: str = ""
    expects: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolItem:
    label: str; type: str; flag: str; short: str = ""; desc: str = ""; severity: str = "system"
    default: Any = ""; default_equipped: bool = False
    hidden: bool = False
    unit: str = ""           
    clone_limit: int = 0     
    options: List[str] = field(default_factory=list)
    expects: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Any] = field(default_factory=dict)
    validation: Dict[str, Union[int, float]] = field(default_factory=dict)

SMART_SCHEMA = {
    "Smart Automations":[
        SmartPreset(
            label="Directed Resync", 
            id="preset_directed_resync", 
            trigger_condition="manual", 
            lifecycle="one_time", 
            auto_apply=False, 
            color="#e74c3c",
            python_hook="audit_resync_environment",
            desc="Automated baseline rebuild. Performs a local environment audit before allowing execution.",
            expects=["--resync-mode"], # Pulls the dropdown but leaves it UNLOCKED for the user
            rejects=["--track-renames"], 
            satisfy={"--resync": True} # Automatically pulls AND LOCKS the dangerous resync flag
        ),
        SmartPreset(
            label="Mount Safety Lock", 
            id="preset_mount_safety", 
            trigger_condition="always_on", 
            lifecycle="persistent", 
            auto_apply=False, 
            color="#f39c12",
            desc="Prevents catastrophic deletion if a drive unmounts by checking for a test file.",
            expects=["--check-filename"],
            satisfy={"--check-access": True} # No expects needed!
        ),
        SmartPreset(
            label="Safe Trash Protection", 
            id="preset_safe_trash", 
            trigger_condition="always_on", 
            lifecycle="persistent", 
            auto_apply=False, 
            color="#2ecc71",
            python_hook="setup_trash_bins",
            desc="Routes deleted/conflicted files to dedicated trash bins with dynamic real-time timestamps.",
            satisfy={
                "--backup-dir1": TRASH_LOCAL_NAME, 
                "--backup-dir2": TRASH_CLOUD_NAME, 
                "--filter": f"- {TRASH_LOCAL_NAME}/**\n- {TRASH_CLOUD_NAME}/**",
                "--conflict-suffix": ".old", 
                "--suffix": ".old", 
                "--suffix-keep-extension": True
            }
        ),
        SmartPreset(
            label="Hub-and-Spoke Strategy",
            id="preset_star_topology",
            desc="Safe automation for multi-device setups. Uses strict circuit breakers to protect the cloud hub.",
            color="#9b59b6",
            trigger_condition="always_on",
            lifecycle="persistent",
            python_hook="verify_star_topology_sentinels",
            satisfy={
                "--check-access": True,
                "--resilient": True,
                "--recover": True,
                "--conflict-resolve": "newer",
                "--max-delete": 5
            }
        ),
        SmartPreset(
            label="Overdrive Sync", 
            id="preset_overdrive_sync", 
            trigger_condition="manual", 
            lifecycle="persistent", 
            auto_apply=False, 
            color="#3498db",
            desc="Pushes parallel operations to the absolute limit with a 5% safety buffer to prevent freezing.",
            expects=["--checkers", "--transfers"], 
            satisfy={
                "--check-sync": "false", # <--- CHANGE THIS TO A STRING
                "--fast-list": True,
                "--no-slow-hash": True
            }
        ),
    ]
}

BISYNC_SCHEMA = {
    "Critical Control":[
        ToolItem(label="Force Resync", type="check", flag="--resync", hidden=True, severity="critical", rejects=["--track-renames"], desc="Resets the sync history by performing a fresh, one-time merge of both paths."),
        ToolItem(label="Resync Mode", type="combo", flag="--resync-mode", hidden=True, options=['newer', 'older', 'larger', 'smaller', 'path1', 'path2'], default="newer", satisfy={"--resync": True}, severity="critical", desc="Winner resolution strategy during a fresh Resync."),
        ToolItem(label="Force Execution", type="check", flag="--force", default=False, severity="critical", desc="Bypasses safety checks. Use with extreme caution!"),
        ToolItem(label="Check Access", type="check", flag="--check-access", hidden=True, desc="Ensures the connection is valid by looking for a specific test file before starting."),
        ToolItem(label="Check Filename", type="entry", flag="--check-filename", hidden=True, desc="The name of the specific 'canary' file to look for (e.g., path/RCLONE_TEST).")
    ],
    "Conflict and Decision Engine":[
        ToolItem(label="Conflict Strategy", type="combo", flag="--conflict-resolve", options=["none", "newer", "older", "larger", "smaller", "path1", "path2"], default="none", severity="decision", desc="Auto-resolver when a file is modified on BOTH sides simultaneously."),
        ToolItem(label="Conflict Loser", type="combo", flag="--conflict-loser", options=["num", "pathname", "delete"], default="num", severity="decision", expects=["--conflict-suffix"], desc="Action to take on the losing version of a conflicting file."),
        ToolItem(label="Conflict Suffix", type="entry", flag="--conflict-suffix", default="conflict", severity="decision", desc="String appended to a conflicting file if it is renamed."),
        ToolItem(label="Compare Engine", type="multi", flag="--compare", options=["size", "modtime", "checksum"], default="size,modtime", severity="operational", desc="Attributes checked to determine if a file has changed.")
    ],
    "Safety Nets":[
        ToolItem(label="Path 1 Trash", type="entry", flag="--backup-dir1", severity="safety", desc="Directory on Path 1 to isolate deleted/overwritten files."),
        ToolItem(label="Path 2 Trash", type="entry", flag="--backup-dir2", severity="safety", desc="Directory on Path 2 to isolate deleted/overwritten files.")
    ],
    "Advanced Tracking":[
        ToolItem(label="Verify Sync", type="combo", flag="--check-sync", options=["true", "false", "only"], default="true", severity="safety", desc="Double-checks the final listing after sync to ensure integrity."),
        ToolItem(label="Remove Empty Dirs", type="check", flag="--remove-empty-dirs", severity="critical", rejects=["--create-empty-src-dirs"], desc="Deletes empty directories on the destination."),
        ToolItem(label="Sync Only Slow Hash", type="check", flag="--slow-hash-sync-only", severity="heuristic", satisfy={"--compare": {"checksum": True}}, rejects=["--no-slow-hash", "--ignore-listing-checksum", "--download-hash"], desc="Skips slow hashes during the check phase (speed), but enforces them during the transfer phase (safety).")
    ],
    "Database and Metadata":[
        ToolItem(label="Workdir Path", type="entry", flag="--workdir", severity="system", rejects=["--cache-dir"], desc="Custom location for the sync database (Defaults to ~/.cache/rclone/bisync)."),
        ToolItem(label="Force Clean Exit", type="check", flag="--force-bad-exit", hidden=True, severity="critical", desc="Clears the 'clean exit' lock, allowing a run even after a crash or interruption."),
        ToolItem(label="No Cleanup", type="check", flag="--no-cleanup", severity="system", desc="Retains temporary listing files after the sync (Useful for debugging)."),
        ToolItem(label="No Slow Hash", type="check", flag="--no-slow-hash", severity="heuristic", satisfy={"--compare": {"checksum": True}}, desc="Skips checksums if the cloud provider has to download the file to calculate them."),
        ToolItem(label="Download Hash", type="check", flag="--download-hash", severity="heuristic", satisfy={"--compare": {"checksum": True}}, rejects=["--no-slow-hash"], desc="Forces hash generation by downloading the full file if no other hash is available."),
        ToolItem(label="Ignore Listing Checksum", type="check", flag="--ignore-listing-checksum", severity="heuristic", desc="Disables retrieving/storing checksums in the listing cache (Speeds up slow remotes).")
    ],
    "Connection Health":[
        ToolItem(label="Resilient Mode", type="check", flag="--resilient", default_equipped=True, severity="operational", desc="Continues syncing the rest of the files even if individual files error out."),
        ToolItem(label="Auto-Recover", type="check", flag="--recover", default_equipped=True, severity="operational", desc="Automatically attempts to recover from an interrupted previous sync."),
        ToolItem(label="Max Lock Time", type="number", flag="--max-lock", default=2, unit="m", validation={"min": 0}, severity="heuristic", desc="Force-start if a previous sync has been stuck/interrupted for this long.")
    ]
}

GLOBAL_SCHEMA = {
    "Critical Control":[
        ToolItem(label="Dry Run", type="check", flag="--dry-run", short="-n", default_equipped=True, severity="safety", desc="Simulation mode. Shows what would happen without touching any files.")
    ],
    "Conflict and Decision Engine":[
        ToolItem(label="Compare Size Only", type="check", flag="--size-only", severity="operational", rejects=["--compare", "--ignore-size"], desc="Ignores timestamps; considers a file changed only if its size differs."),
        ToolItem(label="Ignore Size", type="check", flag="--ignore-size", severity="operational", rejects=["--size-only"], desc="Skips size checks; relies strictly on modtime or checksums.")
    ],
    "Safety Nets":[
        ToolItem(label="Max Delete Count", type="number", flag="--max-delete", default=15, validation={"min": 0}, severity="critical", desc="Aborts the sync if the total deletion count exceeds this number."),
        ToolItem(label="Max Delete Size", type="entry", flag="--max-delete-size", severity="critical", desc="Aborts the sync if the total size of deletions exceeds this limit (e.g., 100M, 2G)."),
        ToolItem(label="Trash Suffix", type="entry", flag="--suffix", severity="safety", desc="Appended to files moved to the trash."),
        ToolItem(label="Keep Extension", type="check", flag="--suffix-keep-extension", severity="safety", desc="Inserts the trash suffix BEFORE the file extension (e.g., file.old.txt).")
    ],
    "Advanced Tracking":[
        ToolItem(label="Track Renames", type="check", flag="--track-renames", severity="heuristic", expects=["--track-renames-strategy"], rejects=["--resync"], desc="Intelligently detects renamed files to minimize re-uploading."),
        ToolItem(label="Rename Strategy", type="combo", flag="--track-renames-strategy", options=["hash", "modtime", "leaf"], default="hash", satisfy={"--track-renames": True}, severity="heuristic", desc="Method used to match renamed files (Hash is safest)."),
        ToolItem(label="Sync Empty Dirs", type="check", flag="--create-empty-src-dirs", severity="operational", rejects=["--remove-empty-dirs"], desc="Synchronizes empty directories."),
        ToolItem(label="Filter Rules", type="text", flag="--filter", clone_limit=-1, severity="decision", desc="Include (+) or Exclude (-) specific file patterns."),
        ToolItem(label="Filters File", type="entry", flag="--filters-file", severity="decision", desc="Path to a text file containing include (+) and exclude (-) patterns.")
    ],
    "System Paths":[
        ToolItem(label="Global Cache Dir", type="entry", flag="--cache-dir", severity="system", desc="Global cache directory for rclone operations. Bisync uses this if --workdir is not set.")
    ],
    "Connection Health":[
        ToolItem(label="Retries", type="number", flag="--retries", default=5, validation={"min": 1}, severity="system", desc="Number of times to retry a failed file transfer."),
        ToolItem(label="Timeout", type="entry", flag="--timeout", default="15m", severity="system", desc="IO idle timeout (e.g., 10m, 1h). Increase this for low-bandwidth connections."),
        ToolItem(label="Ignore Errors", type="check", flag="--ignore-errors", hidden=True, severity="critical", desc="Deletes files on destination even if there were I/O errors reading the source (Dangerous)."),
        ToolItem(label="Verbose Output", type="count", flag="--verbose", short="-v", validation={"max": 1}, severity="system", desc="The app already handles the Level 1 verbosity for logs. Rclone supports increasing log noise upto Level 2 (very verbose: '-vv' or '-v -v')."),
        ToolItem(label="Fast List", type="check", flag="--fast-list", severity="heuristic", desc="Uses fewer API calls by loading the whole directory into RAM. High memory usage!"),
        ToolItem(label="Checkers", type="number", flag="--checkers", default=4, validation={"min": 1}, severity="system", desc="Number of parallel file comparison threads."),
        ToolItem(label="Transfers", type="number", flag="--transfers", default=2, validation={"min": 1}, severity="system", desc="Number of parallel file uploads/downloads."),
    ]
}

# Aggregate them into CONFIG_SCHEMA to maintain complete downstream compatibility.
CONFIG_SCHEMA = {}
for schema in (BISYNC_SCHEMA, GLOBAL_SCHEMA):
    for cat, items in schema.items():
        CONFIG_SCHEMA.setdefault(cat,[]).extend(items)