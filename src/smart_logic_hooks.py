# smart_logic_hooks.py
import os, glob, datetime
from src.workbench_blueprint import TRASH_LOCAL_NAME, TRASH_CLOUD_NAME, RCLONE_CACHE_DIR

def setup_trash_bins(profile, local_path, remote_path, live_state):
    """Prepares the environment for Safe Trashing by calculating absolute paths and dynamic timestamps."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    
    # 1. Inject Dynamic Timestamps for suffixing
    live_state['conflict_suffix'] = f"_{timestamp}.old"
    live_state['suffix'] = f"_{timestamp}.old"
    live_state['suffix_keep_extension'] = True
    
    # 2. Safely resolve local backup directory to an absolute path
    l_trash = live_state.get('backup_path_1', TRASH_LOCAL_NAME)
    full_local_trash = os.path.join(local_path, l_trash) if not os.path.isabs(l_trash) else l_trash
    
    if not os.path.exists(full_local_trash):
        os.makedirs(full_local_trash, exist_ok=True)
        
    live_state['backup_path_1'] = full_local_trash
    
    # 3. Target remote backup directory
    c_trash = live_state.get('backup_path_2', TRASH_CLOUD_NAME)
    live_state['backup_path_2'] = f"{profile}:{c_trash}"
        
    return live_state

def normalize_session_path(profile, local_path, remote_path, live_state):
    """Session Fixer: Renames .lst files to match backend suffixes."""
    anchor_name = os.path.basename(local_path.strip('/')) if local_path else profile
    
    # Example logic: if backend adds {suffix}, ensure existing .lst files are renamed
    target_glob = os.path.join(RCLONE_CACHE_DIR, f"*{anchor_name}*.lst")
    for file_path in glob.glob(target_glob):
        if "{suffix}" not in file_path:  # Pseudo-logic for detecting suffix discrepancy
            new_path = file_path.replace(".lst", "_{suffix}.lst")
            try:
                os.rename(file_path, new_path)
            except OSError:
                pass
                
    return live_state