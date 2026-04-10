import os
from dataclasses import dataclass, field
from typing import List, Dict, Union

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
    satisfy: Dict[str, Union[bool, str, int]] = field(default_factory=dict)

@dataclass
class ToolItem:
    label: str; key: str; type: str; flag: str = ""; short: str = ""; desc: str = ""; color: str = "#ecf0f1"
    default: Union[str, bool, int] = ""; default_equipped: bool = False
    options: List[str] = field(default_factory=list)
    expects: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Union[bool, str, int]] = field(default_factory=dict)
    validation: Dict[str, str] = field(default_factory=dict)

SMART_SCHEMA = {
    "Smart Automations": [
        SmartPreset(
            label="Master Safe Resync", key="preset_master_resync", trigger_condition="missing_listing_file", lifecycle="one_time", auto_apply=False, color="#e74c3c",
            desc="Automated baseline reconciliation for first runs or clearing critical lockouts.",
            expects=["resync", "resync_mode", "resilient", "recover"], rejects=["track_renames"],
            satisfy={"resync": True, "resync_mode": "newer", "resilient": True, "recover": True}
        ),
        SmartPreset(
            label="Safe Trash Protection", key="preset_safe_trash", trigger_condition="always_on", lifecycle="persistent", auto_apply=False, color="#2ecc71",
            python_hook="setup_trash_bins",
            desc="Routes deleted files to dedicated trash bins with dynamic real-time timestamps.",
            expects=["backup_path_1", "backup_path_2", "filter", "conflict_suffix", "suffix", "suffix_keep_extension"],
            satisfy={
                "backup_path_1": TRASH_LOCAL_NAME, "backup_path_2": TRASH_CLOUD_NAME, "filter": f"- {TRASH_LOCAL_NAME}/**\n- {TRASH_CLOUD_NAME}/**",
                "conflict_suffix": ".old", "suffix": ".old", "suffix_keep_extension": True
            }
        )
    ]
}

CONFIG_SCHEMA = {
    "Core Actions": [
        ToolItem(label="Force Full Resync", key="resync", type="check", flag="--resync", color="#e74c3c", rejects=["track_renames"], desc="Mandatory for first runs and state recovery."),
        ToolItem(label="Resync Mode", key="resync_mode", type="combo", flag="--resync-mode", options=['newer', 'older', 'larger'], default="newer", expects=["resync"], color="#e67e22", desc="Strategy for resolving differences."),
        ToolItem(label="Track Renames", key="track_renames", type="check", flag="--track-renames", rejects=["resync"], color="#8e44ad", desc="Track moved files (Mutual exclusion with resync).")
    ],
    "General": [
        ToolItem(label="Compare Mode", key="compare", type="multi", flag="--compare", options=["size", "modtime", "checksum"], default="size,modtime", color="#3498db", desc="Comma-separated list of compare options."),
        ToolItem(label="Conflict Resolve", key="conflict_resolve", type="combo", flag="--conflict-resolve", options=["none", "path1", "path2", "newer", "older", "larger", "smaller"], default="none", color="#e67e22", desc="Automatically prefer a version when a conflict is detected."),
        ToolItem(label="Conflict Loser", key="conflict_loser", type="combo", flag="--conflict-loser", options=["num", "pathname", "delete"], default="num", color="#e67e22", desc="Action to take on the 'loser' file of a sync conflict."),
        ToolItem(label="Conflict Suffix", key="conflict_suffix", type="entry", flag="--conflict-suffix", default="conflict", color="#e67e22", desc="Suffix used when renaming conflicting files."),
        ToolItem(label="Check Access", key="check_access", type="check", flag="--check-access", default=False, color="#2ecc71", desc="Abort if RCLONE_TEST files are not found on both sides."),
        ToolItem(label="Check Filename", key="check_filename", type="entry", flag="--check-filename", default="RCLONE_TEST", color="#2ecc71", expects=["check_access"], desc="Custom filename for the access check."),
        ToolItem(label="Empty Dirs", key="remove_empty_dirs", type="check", flag="--remove-empty-dirs", default=False, color="#9b59b6", rejects=["create_empty_src_dirs"], desc="Remove all empty directories during the final cleanup step."),
        ToolItem(label="Sync Empty Dirs", key="create_empty_src_dirs", type="check", flag="--create-empty-src-dirs", default=False, color="#9b59b6", rejects=["remove_empty_dirs"], desc="Sync the creation and deletion of empty directories."),
        ToolItem(label="Download Hash", key="download_hash", type="check", flag="--download-hash", default=False, color="#f1c40f", desc="Compute hash by downloading if unavailable."),
        ToolItem(label="Force Sync", key="force", type="check", flag="--force", default=False, color="#e74c3c", desc="Bypass max-delete safety checks and run the sync immediately."),
        ToolItem(label="Filters File", key="filters_file", type="entry", flag="--filters-file", default="", color="#f1c40f", desc="Path to a file containing sync filtering patterns.")
    ],
    "Safety": [
        ToolItem(label="Dry Run", key="dry_run", type="check", flag="--dry-run", short="-n", default_equipped=True, color="#2ecc71", desc="Trial run with no permanent changes."),
        ToolItem(label="Backup Local", key="backup_path_1", type="entry", flag="--backup-dir1", color="#2ecc71", desc="Local safety bin."),
        ToolItem(label="Backup Cloud", key="backup_path_2", type="entry", flag="--backup-dir2", color="#2ecc71", desc="Cloud safety bin."),
        ToolItem(label="Backup Suffix", key="suffix", type="entry", flag="--suffix", color="#2ecc71", desc="Suffix appended to backup directory files."),
        ToolItem(label="Keep Extension", key="suffix_keep_extension", type="check", flag="--suffix-keep-extension", color="#2ecc71", desc="Preserve extension when applying suffix."),
        ToolItem(label="Filter", key="filter", type="text", flag="--filter", color="#f1c40f", desc="Rules to exclude trash or system files.")
    ],
    "Engine": [
        ToolItem(label="Resilient", key="resilient", type="check", flag="--resilient", default_equipped=True, color="#3498db", desc="Self-heals from network interruptions."),
        ToolItem(label="Recover", key="recover", type="check", flag="--recover", default_equipped=True, color="#3498db", desc="Auto-recovery for interrupted runs."),
        ToolItem(label="Max Lock", key="max_lock", type="entry", flag="--max-lock", default="2m", color="#9b59b6", desc="Auto-expire stale lock files.", validation={"min": "2m"}),
        ToolItem(label="Verbose Level", key="verbose", type="count", flag="-v", short="-v", color="#95a5a6", desc="Increase log detail.")
    ]
}