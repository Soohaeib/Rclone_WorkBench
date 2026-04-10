import os, glob, datetime

def scan_environment(local_path, remote_profile):
    from src.workbench_blueprint import RCLONE_CACHE_DIR
    anchor = os.path.basename(local_path.strip('/')) if local_path else remote_profile
    base_glob = os.path.join(RCLONE_CACHE_DIR, f"*{anchor}*")
    
    recs = {"preset_safe_trash"}
    if not glob.glob(f"{base_glob}.path1.lst") or glob.glob(f"{base_glob}.path1.lst-err") or glob.glob(f"{base_glob}.lck"):
        recs.add("preset_master_resync")
    return list(recs)

def setup_trash_bins(profile, local_path, remote_path, live_state):
    from src.workbench_blueprint import TRASH_LOCAL_NAME, TRASH_CLOUD_NAME
    ts = f"_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.old"
    live_state.update({'conflict_suffix': ts, 'suffix': ts, 'suffix_keep_extension': True})
    
    l_trash = live_state.get('backup_path_1', TRASH_LOCAL_NAME)
    full_local = os.path.join(local_path, l_trash) if not os.path.isabs(l_trash) else l_trash
    os.makedirs(full_local, exist_ok=True)
    
    live_state['backup_path_1'] = full_local
    live_state['backup_path_2'] = f"{profile}:{live_state.get('backup_path_2', TRASH_CLOUD_NAME)}"
    return live_state