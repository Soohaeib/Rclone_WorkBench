# smart_logic_hooks.py
import os
import workbench_blueprint as blueprint

def setup_trash_bins(profile, local_path, live_state):
    """Triggered by preset_safe_trash to ensure directories and filters exist."""
    l_trash = live_state.get('backup_path_1', blueprint.TRASH_LOCAL_NAME)
    full_local_trash = os.path.join(local_path, l_trash) if not os.path.isabs(l_trash) else l_trash
    
    # Side effect: Create the local trash folder
    os.makedirs(full_local_trash, exist_ok=True)
    
    # Side effect: Inject mandatory filters to avoid syncing the trash itself
    current_filter = live_state.get('filter', '')
    trash_rule = f"- {blueprint.TRASH_LOCAL_NAME}/**"
    if trash_rule not in current_filter:
        live_state['filter'] = f"{trash_rule}\n{current_filter}".strip()
        
    return live_state