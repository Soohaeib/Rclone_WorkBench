import os, glob, datetime, hashlib, configparser

def get_remote_type(profile):
    """Helper to parse rclone.conf for backend capabilities."""
    from src.workbench_blueprint import RCLONE_CONF_PATH
    cp = configparser.ConfigParser()
    if os.path.exists(RCLONE_CONF_PATH):
        cp.read(RCLONE_CONF_PATH)
        if cp.has_section(profile):
            return cp.get(profile, 'type', fallback='')
    return ''

def audit_resync_environment(profile, local_path, remote_path, live_state):
    """
    The 9-Point Environmental Audit.
    Performs a high-speed local filesystem audit of the rclone cache.
    Injects _AUDIT_ERROR keys if critical safety parameters fail.
    """
    from src.workbench_blueprint import RCLONE_CACHE_DIR, APP_DIR
    
    # AUDIT 4: Session Drift. 
    # By anchoring on the folder name and using glob wildcards (*anchor*), 
    # we bypass rclone's canonical suffix generation, surviving flag drift.
    anchor = os.path.basename(local_path.strip('/')) if local_path else profile
    base_glob = os.path.join(RCLONE_CACHE_DIR, f"*{anchor}*")
    
    # PREREQUISITE 1 & 3: Missing Listings & Critical Lockout
    lst_files = glob.glob(f"{base_glob}.path1.lst")
    err_files = glob.glob(f"{base_glob}.path1.lst-err")
    
    is_resync_equipped = live_state.get('resync', False)

    # AUDIT 5: Stale Lock PID Check
    for lck_file in glob.glob(f"{base_glob}.lck"):
        try:
            with open(lck_file, 'r') as f: pid = int(f.read().strip())
            os.kill(pid, 0) # Throws OSError if PID is dead
            live_state['_AUDIT_ERROR_PID'] = f"Active lock found (PID {pid}). Sync in progress. Please wait."
        except OSError:
            if not is_resync_equipped:
                live_state['_AUDIT_ERROR_STALE'] = "Crashed State (.lck) detected. Directed Resync recommended to recover safely."
        except ValueError: pass

    # PREREQUISITE 2 & AUDIT 6: Filter Integrity & Structural Drift
    # We combine user canvas filters into a hash and check our local app tracker.
    filter_text = "\n".join([v for k, v in live_state.items() if k.startswith('filter') and isinstance(v, str)])
    tracker_path = os.path.join(APP_DIR, f"{profile}_filter_state.md5")
    
    if filter_text:
        current_md5 = hashlib.md5(filter_text.encode()).hexdigest()
        if os.path.exists(tracker_path):
            with open(tracker_path, 'r') as f: cached_md5 = f.read().strip()
            if current_md5 != cached_md5 and not is_resync_equipped:
                live_state['_AUDIT_ERROR_FILTER'] = "Filter modification detected. Directed Resync is MANDATORY to prevent mass deletions."
        else:
            # First time seeing filters, save the state quietly (handled fully in post-sync)
            pass

    # AUDIT 7: Empty Path Trap (Local Evaluation for UI Speed)
    if local_path and os.path.exists(local_path):
        try:
            if len(os.listdir(local_path)) == 0 and not is_resync_equipped:
                live_state['_AUDIT_ERROR_EMPTY'] = f"Local path '{anchor}' has 0 files! Resync mandatory to bypass Rclone's safety abort."
        except Exception: pass

    # AUDIT 8: Metadata Capability Validation
    if is_resync_equipped and live_state.get('resync_mode') in ['newer', 'older']:
        rtype = get_remote_type(profile.split(':')[0])
        # Backends known to lack arbitrary modtime support
        if rtype in ['photos', 'ftp', 'memory']: 
            live_state['_AUDIT_ERROR_MODTIME'] = f"Backend '{rtype}' does not support accurate modtimes for '{live_state.get('resync_mode')}'. Use 'path1' or 'size'."

    # AUDIT 9: Access Health Sentinel Check (Local Evaluation)
    if live_state.get('check_access') and live_state.get('check_filename'):
        fname = live_state.get('check_filename')
        if local_path and os.path.exists(local_path):
            if not os.path.exists(os.path.join(local_path, fname)):
                live_state['_AUDIT_ERROR_ACCESS'] = f"Sentinel file '{fname}' missing from Local path! Drive may be unmounted."

    return live_state

def scan_environment(local_path, remote_profile):
    from src.workbench_blueprint import RCLONE_CACHE_DIR
    anchor = os.path.basename(local_path.strip('/')) if local_path else remote_profile
    base_glob = os.path.join(RCLONE_CACHE_DIR, f"*{anchor}*")
    
    recs = {"preset_safe_trash"}
    if not glob.glob(f"{base_glob}.path1.lst") or glob.glob(f"{base_glob}.path1.lst-err") or glob.glob(f"{base_glob}.lck"):
        recs.add("preset_directed_resync")
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