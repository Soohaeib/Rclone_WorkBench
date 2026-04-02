import os

# --- Path Definitions ---
APP_DIR = os.path.expanduser('~/Scripts/WorkBench')
# This is the line that was missing:
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
            "label": "Safe Trash Protection",
            "key": "preset_safe_trash",
            "lifecycle": "persistent",
            "python_hook": "setup_trash_bins",
            "color": "#2ecc71",
            "desc": "Routes deleted files to dedicated local/cloud trash bins.",
            "expects": ["backup_path_1", "backup_path_2", "filter"]
        },
        {
            "label": "Resilient Sync (Failsafe)",
            "key": "preset_resilient",
            "lifecycle": "persistent",
            "color": "#d35400",
            "desc": "Enables auto-recovery and extends locks for unstable connections.",
            "expects": ["resilient", "recover", "max_lock"],
            "satisfy": {"max_lock": "5m"}
        }
    ]
}

# --- The Config Schema (Tools) ---
CONFIG_SCHEMA = {
    "Core Actions": [
        {"label": "Force Full Resync", "key": "resync", "type": "check", "flag": "--resync", "color": "#e74c3c"},
        {"label": "Resync Mode", "key": "resync_mode", "type": "combo", "flag": "--resync-mode", "options": ['newer', 'older', 'larger'], "default": "newer", "expects": ["resync"]}
    ],
    "Safety": [
        {"label": "Backup Local", "key": "backup_path_1", "type": "entry", "flag": "--backup-dir1"},
        {"label": "Backup Cloud", "key": "backup_path_2", "type": "entry", "flag": "--backup-dir2"},
        {"label": "Filter", "key": "filter", "type": "stack", "flag": "--filter"}
    ],
    "Engine": [
         {"label": "Resilient", "key": "resilient", "type": "check", "flag": "--resilient"},
         {"label": "Recover", "key": "recover", "type": "check", "flag": "--recover"},
         {"label": "Max Lock", "key": "max_lock", "type": "entry", "flag": "--max-lock", "default": "2m"}
    ]
}