import os
from dataclasses import dataclass, field
from typing import List, Dict, Union, Any

APP_DIR = os.path.expanduser('~/Scripts/Rclone_WorkBench')
RCLONE_CONF_PATH = os.path.expanduser('~/.config/rclone/rclone.conf')
RCLONE_CACHE_DIR = os.path.expanduser('~/.cache/rclone/bisync')
JSON_CONFIG_FILE = os.path.join(APP_DIR, 'bisync_settings.json')
LOG_DIR = os.path.join(APP_DIR, 'logs')

TRASH_LOCAL_NAME = '.rclone_trash_local'
TRASH_CLOUD_NAME = '.rclone_trash_cloud'

@dataclass
class SmartPreset:
    label: str; id: str; desc: str; color: str = "#3498db"
    trigger_condition: str = "manual"; lifecycle: str = "persistent"
    auto_apply: bool = False; python_hook: str = ""
    expects: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolItem:
    label: str; type: str; flag: str; short: str = ""; desc: str = ""; color: str = "#ecf0f1"
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
    "Smart Automations": [
        SmartPreset(
            label="Directed Resync", 
            id="preset_directed_resync", 
            trigger_condition="manual", 
            lifecycle="one_time", 
            auto_apply=False, 
            color="#e74c3c",
            python_hook="audit_resync_environment",
            desc="Automated baseline rebuild. Performs a local environment audit before allowing execution.",
            expects=["--resync-mode", "--resync"], 
            rejects=["--track-renames"], 
            satisfy={"--resync": True}   
        ),
        SmartPreset(
            label="Mount Safety Lock", id="preset_mount_safety", trigger_condition="always_on", lifecycle="persistent", auto_apply=False, color="#f39c12",
            desc="Prevents catastrophic deletion if a drive unmounts by checking for a test file. (Triggers --check-access)",
            expects=["--check-access", "--check-filename"],
            satisfy={"--check-access": True, "--check-filename": "RCLONE_TEST"}
        ),
        SmartPreset(
            label="Safe Trash Protection", id="preset_safe_trash", trigger_condition="always_on", lifecycle="persistent", auto_apply=False, color="#2ecc71",
            python_hook="setup_trash_bins",
            desc="Routes deleted/conflicted files to dedicated trash bins with dynamic real-time timestamps.",
            expects=["--backup-dir1", "--backup-dir2", "--filter", "--conflict-suffix", "--suffix", "--suffix-keep-extension"],
            satisfy={
                "--backup-dir1": TRASH_LOCAL_NAME, "--backup-dir2": TRASH_CLOUD_NAME, "--filter": f"- {TRASH_LOCAL_NAME}/**\n- {TRASH_CLOUD_NAME}/**",
                "--conflict-suffix": ".old", "--suffix": ".old", "--suffix-keep-extension": True
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
            expects=["--check-access", "--resilient", "--recover", "--conflict-resolve"],
            satisfy={
                "--check-access": True,
                "--resilient": True,
                "--recover": True,
                "--conflict-resolve": "newer",
                "--max-delete": 5
            }
        )
    ]
}

CONFIG_SCHEMA = {
    "Hidden System Flags": [
        ToolItem(label="Force Resync", type="check", flag="--resync", hidden=True, rejects=["--track-renames"], desc="Establishes a matching superset of files on both paths to create a new baseline."),
        ToolItem(label="Resync Mode", type="combo", flag="--resync-mode", options=['newer', 'older', 'larger', 'smaller', 'path1', 'path2'], default="newer", hidden=True, expects=["--resync"], desc="Winner resolution during a resync."),
        ToolItem(label="Check Access", type="check", flag="--check-access", hidden=True, desc="Aborts if the test file isn't found."),
        ToolItem(label="Check Filename", type="entry", flag="--check-filename", hidden=True, desc="Name of the access test file.")
    ],
    "Bisync Rules": [
        ToolItem(label="Compare Engine", type="multi", flag="--compare", options=["size", "modtime", "checksum"], color="#3498db", desc="Attributes checked to determine if a file has changed."),
        ToolItem(label="Conflict Strategy", type="combo", flag="--conflict-resolve", options=["none", "newer", "older", "larger", "smaller", "path1", "path2"], default="none", color="#e67e22", desc="Auto-resolver when a file is modified on BOTH sides simultaneously."),
        ToolItem(label="Conflict Loser", type="combo", flag="--conflict-loser", options=["num", "pathname", "delete"], default="num", color="#e67e22", expects=["--conflict-suffix"], desc="What happens to the overwritten file during a conflict."),
        ToolItem(label="Conflict Suffix", type="entry", flag="--conflict-suffix", default="conflict", color="#e67e22", desc="String appended to a conflicting file if it is renamed instead of deleted."),
        ToolItem(label="Sync Empty Dirs", type="check", flag="--create-empty-src-dirs", color="#48b6ff", rejects=["--remove-empty-dirs"], desc="Sync empty directories."),
        ToolItem(label="Remove Empty Dirs", type="check", flag="--remove-empty-dirs", color="#48b6ff", rejects=["--create-empty-src-dirs"], desc="Remove empty directories."),
        ToolItem(label="Force Execution", type="check", flag="--force", default=False, color="#e74c3c", desc="Bypasses safety checks. Use with caution!")
    ],
    "Safety and Trash": [
        ToolItem(label="Dry Run", type="check", flag="--dry-run", short="-n", default_equipped=True, color="#2ecc71", desc="Trial run. Shows what would happen without making any actual changes."),
        ToolItem(label="Local Trash", type="entry", flag="--backup-dir1", color="#2ecc71", desc="Directory to store deleted/overwritten local files."),
        ToolItem(label="Cloud Trash", type="entry", flag="--backup-dir2", color="#2ecc71", desc="Directory to store deleted/overwritten cloud files."),
        ToolItem(label="Trash Suffix", type="entry", flag="--suffix", color="#2ecc71", desc="Appended to files moved to the trash."),
        ToolItem(label="Keep Extension", type="check", flag="--suffix-keep-extension", color="#2ecc71", desc="Puts the trash suffix BEFORE the file extension."),
        ToolItem(label="Max Delete", type="number", flag="--max-delete", default=50, validation={"min": 0, "max": 100}, color="#e74c3c", desc="Safety threshold: Maximum percentage of deletions allowed."),
        ToolItem(label="Filter Rules", type="text", flag="--filter", clone_limit=-1, color="#f1c40f", desc="Include (+) or Exclude (-) specific file patterns.")
    ],
    "Engine Health": [
        ToolItem(label="Resilient Mode", type="check", flag="--resilient", default_equipped=True, color="#3498db", desc="Continues syncing even if some files fail to transfer."),
        ToolItem(label="Auto-Recover", type="check", flag="--recover", default_equipped=True, color="#3498db", desc="Automatically recovers from an interrupted previous sync."),
        ToolItem(label="Max Lock Time", type="number", flag="--max-lock", default=2, unit="m", validation={"min": 0}, color="#9b59b6", desc="Time before a stale sync lock is automatically ignored."),
        ToolItem(label="Verbose Output", type="count", flag="--verbose", short="-v", validation={"min": 0, "max": 3}, color="#95a5a6", desc="Increases the detail of the log output. Up to -v -v -v.")
    ],
    "Advanced Flags": [
        ToolItem(label="Track Renames", type="check", flag="--track-renames", color="#9b59b6", rejects=["--resync"], desc="Detects renamed files instead of treating them as delete+create."),
        ToolItem(label="Ignore Listing Checksum", type="check", flag="--ignore-listing-checksum", color="#9b59b6", rejects=["--no-slow-hash", "--slow-hash-sync-only", "--download-hash"], desc="Disables retrieving/storing checksums in listing files."),
        ToolItem(label="No Slow Hash", type="check", flag="--no-slow-hash", color="#9b59b6", expects=["--compare"], satisfy={"--compare": {"checksum": True}}, rejects=["--ignore-listing-checksum", "--slow-hash-sync-only", "--download-hash"], desc="Automatically skips checksums on remotes where they must be computed on-the-fly."),
        ToolItem(label="Sync Only for Slow Hash", type="check", flag="--slow-hash-sync-only", color="#9b59b6", expects=["--compare"], satisfy={"--compare": {"checksum": True}}, rejects=["--ignore-listing-checksum", "--no-slow-hash", "--download-hash"], desc="Skips slow hashes when scanning for changes, but still performs hash verification during transfer."),
        ToolItem(label="Download Hash", type="check", flag="--download-hash", color="#9b59b6", rejects=["--ignore-listing-checksum", "--no-slow-hash", "--slow-hash-sync-only"], desc="Forces hash generation by downloading the full file if no other hash is available.")
    ]
}