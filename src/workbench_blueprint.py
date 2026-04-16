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
    label: str; key: str; desc: str; color: str = "#3498db"
    trigger_condition: str = "manual"; lifecycle: str = "persistent"
    auto_apply: bool = False; python_hook: str = ""
    expects: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolItem:
    label: str; key: str; type: str; flag: str = ""; short: str = ""; desc: str = ""; color: str = "#ecf0f1"
    default: Any = ""; default_equipped: bool = False
    hidden: bool = False
    unit: str = ""           # NEW: Automatically appends to CLI arg (e.g., 'm' for minutes)
    clone_limit: int = 0     # NEW: -1 = Infinite splits, 0 = No splits, >0 = Max splits
    options: List[str] = field(default_factory=list)
    expects: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Any] = field(default_factory=dict)
    validation: Dict[str, Union[int, float]] = field(default_factory=dict)

SMART_SCHEMA = {
    "Smart Automations": [
        SmartPreset(
            label="Directed Resync", 
            key="preset_directed_resync", 
            trigger_condition="manual", 
            lifecycle="one_time", # Drops automatically on exit 0
            auto_apply=False, 
            color="#e74c3c",
            python_hook="audit_resync_environment", # Triggers our new audit
            desc="Automated baseline rebuild. Performs a local environment audit before allowing execution.",
            expects=["resync_mode"], 
            rejects=["track_renames"], # Enforces technical constraint
            satisfy={"resync": True}   # Locks the dangerous flag
        ),
        SmartPreset(
            label="Mount Safety Lock", key="preset_mount_safety", trigger_condition="always_on", lifecycle="persistent", auto_apply=False, color="#f39c12",
            desc="Prevents catastrophic deletion if a drive unmounts by checking for a test file. (Triggers --check-access)",
            expects=["check_access", "check_filename"],
            satisfy={"check_access": True, "check_filename": "RCLONE_TEST"}
        ),
        SmartPreset(
            label="Safe Trash Protection", key="preset_safe_trash", trigger_condition="always_on", lifecycle="persistent", auto_apply=False, color="#2ecc71",
            python_hook="setup_trash_bins",
            desc="Routes deleted/conflicted files to dedicated trash bins with dynamic real-time timestamps.",
            expects=["backup_path_1", "backup_path_2", "filter", "conflict_suffix", "suffix", "suffix_keep_extension"],
            satisfy={
                "backup_path_1": TRASH_LOCAL_NAME, "backup_path_2": TRASH_CLOUD_NAME, "filter": f"- {TRASH_LOCAL_NAME}/**\n- {TRASH_CLOUD_NAME}/**",
                "conflict_suffix": ".old", "suffix": ".old", "suffix_keep_extension": True
            }
        ),
        SmartPreset(
            label="Hub-and-Spoke Strategy",
            key="preset_star_topology",
            desc="Safe automation for multi-device setups. Uses strict circuit breakers to protect the cloud hub.",
            color="#9b59b6",
            trigger_condition="always_on",
            lifecycle="persistent",
            python_hook="verify_star_topology_sentinels",
            expects=["check_access", "resilient", "recover", "conflict_resolve"],
            satisfy={
                "check_access": True,
                "resilient": True,
                "recover": True,
                "conflict_resolve": "newer",
                "max_delete": 5  # Circuit breaker threshold
            }
        )
    ]
}

CONFIG_SCHEMA = {
    "Hidden System Flags": [
        # These are hidden from the user sandbox and managed strictly by Smart Presets
        ToolItem(label="Force Resync", key="resync", type="check", flag="--resync", hidden=True, desc="Rebuilds the sync database from scratch."),
        ToolItem(label="Resync Mode", key="resync_mode", type="combo", flag="--resync-mode", options=['newer', 'older', 'larger', 'smaller', 'path1', 'path2'], default="newer", hidden=True, desc="Winner resolution during a resync."),
        ToolItem(label="Check Access", key="check_access", type="check", flag="--check-access", hidden=True, desc="Aborts if the test file isn't found."),
        ToolItem(label="Check Filename", key="check_filename", type="entry", flag="--check-filename", hidden=True, desc="Name of the access test file.")
    ],
    "Bisync Rules": [
        ToolItem(label="Compare Engine", key="compare", type="multi", flag="--compare", options=["size", "modtime", "checksum"], color="#3498db", desc="Attributes checked to determine if a file has changed. (rclone.org/bisync/#compare)"),
        ToolItem(label="Conflict Strategy", key="conflict_resolve", type="combo", flag="--conflict-resolve", options=["none", "newer", "older", "larger", "smaller", "path1", "path2"], default="none", color="#e67e22", desc="Auto-resolver when a file is modified on BOTH sides simultaneously. (rclone.org/bisync/#conflict-resolve)"),
        ToolItem(label="Conflict Loser", key="conflict_loser", type="combo", flag="--conflict-loser", options=["num", "pathname", "delete"], default="num", color="#e67e22", expects=["conflict_suffix"], desc="What happens to the overwritten file during a conflict. (rclone.org/bisync/#conflict-loser)"),
        ToolItem(label="Conflict Suffix", key="conflict_suffix", type="entry", flag="--conflict-suffix", default="conflict", color="#e67e22", desc="String appended to a conflicting file if it is renamed instead of deleted."),
        ToolItem(label="Sync Empty Dirs", key="create_empty_src_dirs", type="check", flag="--create-empty-src-dirs", color="#48b6ff", desc="Sync empty directories."),
        ToolItem(label="Remove Empty Dirs", key="remove_empty_dirs", type="check", flag="--remove-empty-dirs", color="#48b6ff", desc="Remove empty directories."),
        ToolItem(label="Force Execution", key="force", type="check", flag="--force", default=False, color="#e74c3c", desc="Bypasses safety checks (like aborting if too many files were deleted). Use with caution!")
    ],
    "Safety and Trash": [
        ToolItem(label="Dry Run", key="dry_run", type="check", flag="--dry-run", short="-n", default_equipped=True, color="#2ecc71", desc="Trial run. Shows what would happen without making any actual changes."),
        ToolItem(label="Local Trash", key="backup_path_1", type="entry", flag="--backup-dir1", color="#2ecc71", desc="Directory to store deleted/overwritten local files."),
        ToolItem(label="Cloud Trash", key="backup_path_2", type="entry", flag="--backup-dir2", color="#2ecc71", desc="Directory to store deleted/overwritten cloud files."),
        ToolItem(label="Trash Suffix", key="suffix", type="entry", flag="--suffix", color="#2ecc71", desc="Appended to files moved to the trash to prevent overwriting old trash."),
        ToolItem(label="Keep Extension", key="suffix_keep_extension", type="check", flag="--suffix-keep-extension", color="#2ecc71", desc="Puts the trash suffix BEFORE the file extension (e.g. file_trash.txt)."),
        ToolItem(label="Max Delete", key="max_delete", type="number", flag="--max-delete", default=50, validation={"min": 0, "max": 100}, color="#e74c3c", desc="Safety threshold: Maximum percentage of deletions allowed."),
        ToolItem(label="Filter Rules", key="filter", type="text", flag="--filter", clone_limit=-1, color="#f1c40f", desc="Include (+) or Exclude (-) specific file patterns.")
    ],
    "Engine Health": [
        ToolItem(label="Resilient Mode", key="resilient", type="check", flag="--resilient", default_equipped=True, color="#3498db", desc="Continues syncing even if some files fail to transfer."),
        ToolItem(label="Auto-Recover", key="recover", type="check", flag="--recover", default_equipped=True, color="#3498db", desc="Automatically recovers from an interrupted previous sync."),
        ToolItem(label="Max Lock Time", key="max_lock", type="number", flag="--max-lock", default=2, unit="m", validation={"min": 0}, color="#9b59b6", desc="Time before a stale sync lock is automatically ignored."),
        ToolItem(label="Verbose Output", key="verbose", type="count", flag="--verbose", short="-v", validation={"min": 0, "max": 3}, color="#95a5a6", desc="Increases the detail of the log output. Up to -v -v -v.")
    ],
    "Advanced Flags": [
        ToolItem(label="Track Renames", key="track_renames", type="check", flag="--track-renames", default=False, color="#9b59b6", desc="Detects renamed files instead of treating them as delete+create. Can cause issues if files are frequently renamed."),
        ToolItem(label="Ignore Listing Checksum", key="ignore_listing_checksum", type="check", flag="--ignore-listing-checksum", default=False, color="#9b59b6", expects=["compare"], satisfy={"compare": "checksum"}, desc="Skips checksum verification during directory listing. May speed up syncs with large numbers of files but can miss changes if the provider doesn't update modtime on content change."),
        ToolItem(label="No Slow Hash", key="no_slow_hash", type="check", flag="--no-slow-hash", default=False, color="#9b59b6", expects=["compare"], satisfy={"compare": "checksum"}, desc="Skips hashing of files that are the same size. Can speed up syncs but may miss changes if the provider doesn't update modtime on content change."),
        ToolItem(label="Sync Only for Slow Hash", key="slow_hash_sync_only", type="check", flag="--slow-hash-sync-only", default=False, color="#9b59b6", expects=["compare"], satisfy={"compare": "checksum"}, desc="Only syncs files that require a slow hash check. Can speed up syncs but may miss changes if the provider doesn't update modtime on content change."),
        ToolItem(label="Download Hash", key="download_hash", type="check", flag="--download-hash", default=False, color="#9b59b6", rejects=["no_slow_hash"], desc="Compute hashes by downloading the file if the cloud provider doesn't support hashes."),

    ]
}