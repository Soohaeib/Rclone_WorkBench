# smart_automations.py
import os
import glob

def scan_environment(local_path, remote_profile):
    """
    Scans the local filesystem state to recommend Smart Presets.
    """
    recommendations = ["preset_safe_trash"] 
    
    cache_dir = os.path.expanduser("~/.cache/rclone/bisync")
    anchor_name = os.path.basename(local_path.strip('/')) if local_path else remote_profile
    session_glob = f"*{anchor_name}*"

    # Look for standard listings, error-state listings, and deadlocks
    lst_files = glob.glob(os.path.join(cache_dir, f"{session_glob}.path1.lst"))
    err_files = glob.glob(os.path.join(cache_dir, f"{session_glob}.path1.lst-err"))
    lck_files = glob.glob(os.path.join(cache_dir, f"{session_glob}.lck"))

    # TRIGGER LOGIC: Identify Initialization OR Critical Failure
    if not lst_files or err_files or len(lck_files) > 0:
        recommendations.append("preset_master_resync")

    return list(set(recommendations))