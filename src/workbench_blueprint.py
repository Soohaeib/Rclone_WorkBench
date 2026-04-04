# workbench_blueprint.py
import os

# --- Path Definitions ---
APP_DIR = os.path.expanduser('~/Scripts/WorkBench')
RCLONE_CONF_PATH = os.path.expanduser('~/.config/rclone/rclone.conf')
JSON_CONFIG_FILE = os.path.join(APP_DIR, 'bisync_settings.json')
LOG_DIR = os.path.join(APP_DIR, 'logs')

# --- Trash Naming Conventions ---
TRASH_LOCAL_NAME = '.rclone_trash_local'
TRASH_CLOUD_NAME = '.rclone_trash_cloud'

# --- The Smart Schema (Procedures) ---
SMART_SCHEMA = {
    "Smart Automations": [
        {
            "label": "Master Safe Resync",
            "key": "preset_master_resync",
            "trigger_condition": "missing_listing_file", 
            "lifecycle": "one_time",  
            "auto_apply": False,       
            "color": "#e74c3c",       
            "desc": "Automated baseline reconciliation for first runs or clearing critical lockouts.",
            "expects": ["resync", "resync_mode", "resilient", "recover", "verbose"],
            "rejects": ["track_renames"], 
            "satisfy": {
                "resync": False, 
                "resync_mode": "newer", 
                "resilient": False,      
                "recover": False,        
                "verbose": 2
            }
        },
        {
            "label": "Safe Trash Protection",
            "key": "preset_safe_trash",
            "trigger_condition": "always_on",
            "lifecycle": "persistent",
            "auto_apply": False,
            "python_hook": "setup_trash_bins",
            "color": "#2ecc71",       
            "desc": "Persistent delete protection routing files to dedicated safety bins.",
            "expects": ["backup_path_1", "backup_path_2", "filter"],
            "satisfy": {
                "backup_path_1": TRASH_LOCAL_NAME,
                "backup_path_2": TRASH_CLOUD_NAME,
                "filter": "- .rclone_trash_local \&\ - .rclone_trash_cloud"
            }
        }
    ]
}

# --- The Config Schema (Tools) ---
CONFIG_SCHEMA = {
  "General": [
        {
            "label": "Compare Mode",
            "key": "compare",
            "type": "entry",
            "flag": "--compare",
            "default": "size,modtime",
            "color": "#3498db",
            "desc": "Comma-separated list of compare options (size, modtime, checksum)."
        },
        {
            "label": "Conflict Resolve",
            "key": "conflict_resolve",
            "type": "combo",
            "flag": "--conflict-resolve",
            "options": ["none", "path1", "path2", "newer", "older", "larger", "smaller"],
            "default": "none",
            "color": "#e67e22",
            "desc": "Automatically prefer a version when a conflict is detected."
        },
        {
            "label": "Conflict Loser",
            "key": "conflict_loser",
            "type": "combo",
            "flag": "--conflict-loser",
            "options": ["num", "pathname", "delete"],
            "default": "num",
            "color": "#e67e22",
            "desc": "Action to take on the 'loser' file of a sync conflict."
        },
        {
            "label": "Conflict Suffix",
            "key": "conflict_suffix",
            "type": "entry",
            "flag": "--conflict-suffix",
            "default": "conflict",
            "color": "#e67e22",
            "desc": "Suffix used when renaming conflicting files."
        },
        {
            "label": "Check Access",
            "key": "check_access",
            "type": "check",
            "flag": "--check-access",
            "default": False,
            "color": "#2ecc71",
            "desc": "Abort if RCLONE_TEST files are not found on both sides."
        },
        {
            "label": "Check Filename",
            "key": "check_filename",
            "type": "entry",
            "flag": "--check-filename",
            "default": "RCLONE_TEST",
            "color": "#2ecc71",
            "desc": "Custom filename for the access check.",
            "expects": ["check_access"]
        },
        {
            "label": "Empty Dirs",
            "key": "remove_empty_dirs",
            "type": "check",
            "flag": "--remove-empty-dirs",
            "default": False,
            "color": "#9b59b6",
            "desc": "Remove all empty directories during the final cleanup step.",
            "rejects": ["create_empty_src_dirs"]
        },
        {
            "label": "Sync Empty Dirs",
            "key": "create_empty_src_dirs",
            "type": "check",
            "flag": "--create-empty-src-dirs",
            "default": False,
            "color": "#9b59b6",
            "desc": "Sync the creation and deletion of empty directories.",
            "rejects": ["remove_empty_dirs"]
        },
        {
            "label": "Download Hash",
            "key": "download_hash",
            "type": "check",
            "flag": "--download-hash",
            "default": False,
            "color": "#f1c40f",
            "desc": "Compute hash by downloading if unavailable (Warning: high data usage)."
        },
        {
            "label": "Force Sync",
            "key": "force",
            "type": "check",
            "flag": "--force",
            "default": False,
            "color": "#e74c3c",
            "desc": "Bypass max-delete safety checks and run the sync immediately."
        },
        {
            "label": "Filters File",
            "key": "filters_file",
            "type": "entry",
            "flag": "--filters-file",
            "default": "",
            "color": "#f1c40f",
            "desc": "Path to a file containing sync filtering patterns."
        }
    ]
}