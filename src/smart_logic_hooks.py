# smart_logic_hooks.py
import os
import glob
import src.workbench_blueprint as blueprint

def setup_trash_bins(profile, local_path, remote_path, live_state):
    """Prepares the environment for Safe Trashing and prevents sync loops."""
    l_trash = live_state.get('backup_path_1', blueprint.TRASH_LOCAL_NAME)
    full_local_trash = os.path.join(local_path, l_trash) if not os.path.isabs(l_trash) else l_trash
    
    if not os.path.exists(full_local_trash):
        os.makedirs(full_local_trash, exist_ok=True)
    
    current_filters = live_state.get('filter', [])
    if isinstance(current_filters, str):
        current_filters = [f.strip() for f in current_filters.split('\n') if f.strip()]

    required_rules = [
        f"- {blueprint.TRASH_LOCAL_NAME}/**",
        f"- {blueprint.TRASH_CLOUD_NAME}/**"
    ]
    
    modified = False
    for rule in required_rules:
        if rule not in current_filters:
            current_filters.append(rule)
            modified = True
            
    if modified:
        live_state['filter'] = "\n".join(current_filters)
        
    return live_state

def normalize_session_path(profile, local_path, remote_path, live_state):
    """Session Fixer: Renames .lst files to match backend suffixes."""
    cache_dir = os.path.expanduser("~/.cache/rclone/bisync")
    anchor_name = os.path.basename(local_path.strip('/')) if local_path else profile
    
    # Example logic: if backend adds {suffix}, ensure existing .lst files are renamed
    target_glob = os.path.join(cache_dir, f"*{anchor_name}*.lst")
    for file_path in glob.glob(target_glob):
        if "{suffix}" not in file_path:  # Pseudo-logic for detecting suffix discrepancy
            new_path = file_path.replace(".lst", "_{suffix}.lst")
            try:
                os.rename(file_path, new_path)
            except OSError:
                pass
                
    return live_state