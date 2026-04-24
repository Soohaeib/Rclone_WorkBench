import os, glob, datetime, hashlib, configparser

def get_remote_type(profile):
    from src.workbench_blueprint import RCLONE_CONF_PATH
    cp = configparser.ConfigParser()
    if os.path.exists(RCLONE_CONF_PATH):
        cp.read(RCLONE_CONF_PATH)
        if cp.has_section(profile):
            return cp.get(profile, 'type', fallback='')
    return ''

def get_active_workdir(live_state):
    from src.workbench_blueprint import RCLONE_CACHE_DIR
    if live_state.get('--workdir'):
        return os.path.expanduser(live_state['--workdir'])
    if live_state.get('--cache-dir'):
        return os.path.join(os.path.expanduser(live_state['--cache-dir']), 'bisync')
    return RCLONE_CACHE_DIR

def audit_resync_environment(profile, local_path, remote_path, live_state):
    from src.workbench_blueprint import APP_DIR
    from src import config_manager
    
    workdir = get_active_workdir(live_state)
    anchor = os.path.basename(local_path.strip('/')) if local_path else profile
    base_glob = os.path.join(workdir, f"*{anchor}*")
    
    lst_files = glob.glob(f"{base_glob}.path1.lst")
    err_files = glob.glob(f"{base_glob}.path1.lst-err")
    is_resync_equipped = live_state.get('--resync', False)

    for lck_file in glob.glob(f"{base_glob}.lck"):
        try:
            with open(lck_file, 'r') as f: pid = int(f.read().strip())
            os.kill(pid, 0)
            live_state['_AUDIT_ERROR_PID'] = f"Active lock found (PID {pid}). Sync in progress. Please wait."
        except OSError:
            if not is_resync_equipped:
                live_state['_AUDIT_ERROR_STALE'] = "Crashed State (.lck) detected. Directed Resync recommended to recover safely."
        except ValueError: pass

    # --- HASH AUDIT LOGIC (VERIFIED) ---
    filter_text = "\n".join([v for k, v in live_state.items() if k.startswith('--filter') and isinstance(v, str)])
    cfg = config_manager.load_config()
    cached_md5 = cfg.get('filter_hashes', {}).get(profile)

    if filter_text:
        current_md5 = hashlib.md5(filter_text.encode()).hexdigest()
        if cached_md5 is not None and current_md5 != cached_md5 and not is_resync_equipped:
            live_state['_AUDIT_ERROR_FILTER'] = "Filter modification detected. Directed Resync is MANDATORY to prevent mass deletions."
    elif cached_md5 is not None and not is_resync_equipped:
        live_state['_AUDIT_ERROR_FILTER'] = "Filters were completely removed. Directed Resync is MANDATORY to prevent mass deletions."


    # --- DIRECTED RESYNC SAFETY CHECKS (HARDENED) ---
    if is_resync_equipped and local_path and os.path.exists(local_path):
        try:
            if not os.listdir(local_path):
                live_state['_AUDIT_ERROR_EMPTY'] = f"DANGER: Local path '{anchor}' is empty. A Resync under these conditions would DELETE ALL cloud files. Aborting."
        except Exception as e:
            live_state['_AUDIT_ERROR_PATH'] = f"Cannot read local path '{anchor}': {e}"

    if is_resync_equipped and live_state.get('--resync-mode') in ['newer', 'older']:
        rtype = get_remote_type(profile.split(':')[0])
        if rtype in['photos', 'ftp', 'memory']: 
            live_state['_AUDIT_ERROR_MODTIME'] = f"Backend '{rtype}' does not support accurate modtimes for '{live_state.get('--resync-mode')}'. Use 'path1' or 'size' to avoid data loss."

    if live_state.get('--check-access') and live_state.get('--check-filename'):
        fname = live_state.get('--check-filename')
        if local_path and os.path.exists(local_path):
            if not os.path.exists(os.path.join(local_path, fname)):
                live_state['_AUDIT_ERROR_ACCESS'] = f"Sentinel file '{fname}' missing from Local path! Drive may be unmounted."

    return live_state

def scan_environment(local_path, remote_profile, profile_cfg=None):
    if profile_cfg is None: profile_cfg = {}
    workdir = get_active_workdir(profile_cfg)
    
    anchor = os.path.basename(local_path.strip('/')) if local_path else remote_profile
    base_glob = os.path.join(workdir, f"*{anchor}*")
    
    recs = {"preset_safe_trash"}
    if not glob.glob(f"{base_glob}.path1.lst") or glob.glob(f"{base_glob}.path1.lst-err") or glob.glob(f"{base_glob}.lck"):
        recs.add("preset_directed_resync")
    return list(recs)

def setup_trash_bins(profile, local_path, remote_path, live_state):
    from src.workbench_blueprint import TRASH_LOCAL_NAME, TRASH_CLOUD_NAME
    ts = f"_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.old"
    live_state.update({'--conflict-suffix': ts, '--suffix': ts, '--suffix-keep-extension': True})
    
    l_trash = live_state.get('--backup-dir1', TRASH_LOCAL_NAME)
    full_local = os.path.join(local_path, l_trash) if not os.path.isabs(l_trash) else l_trash
    os.makedirs(full_local, exist_ok=True)
    
    live_state['--backup-dir1'] = full_local
    live_state['--backup-dir2'] = f"{profile}:{live_state.get('--backup-dir2', TRASH_CLOUD_NAME)}"
    return live_state

def enforce_checksum_dependency(profile, local_path, remote_path, live_state):
    compare_val = str(live_state.get('--compare', ''))
    if 'checksum' not in compare_val:
        live_state['_AUDIT_ERROR_HASH'] = "This Advanced Flag requires 'checksum' to be enabled in the Compare Engine."
    return live_state

def verify_star_topology_sentinels(profile, local_path, remote_path, live_state):
    if live_state.get('--check-access'):
        fname = live_state.get('--check-filename', 'RCLONE_TEST')
        if live_state.get('--max-delete', 100) > 10:
            live_state['_AUDIT_ERROR_TOPOLOGY'] = "Hub-and-Spoke requires --max-delete to be 10% or lower to prevent cascading mass deletions across devices."
            
    return live_state