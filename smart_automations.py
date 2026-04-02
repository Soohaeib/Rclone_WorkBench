# smart_automations.py
import os, glob
from workbench_blueprint import SMART_SCHEMA

def scan_environment(profile, local_path):
    """Recommends presets based on the file system state."""
    recommendations = []
    
    # If no listing files exist, suggest Resilient Sync for auto-recovery
    lck_files = glob.glob(os.path.expanduser(f'~/.cache/rclone/bisync/*{profile}*.lst'))
    if not lck_files:
        recommendations.append("preset_resilient")
        
    # Always recommend Safe Trash protection
    recommendations.append("preset_safe_trash")
    
    return recommendations