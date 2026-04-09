import os, json
from src.workbench_blueprint import APP_DIR, JSON_CONFIG_FILE, CONFIG_SCHEMA

def load_config():
    if not os.path.exists(JSON_CONFIG_FILE):
        return {"local_paths": {}, "remote_configs": {}}
    try:
        with open(JSON_CONFIG_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"local_paths": {}, "remote_configs": {}}

def save_config(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(JSON_CONFIG_FILE, 'w') as f: json.dump(cfg, f, indent=4)

def ensure_profile_exists(profile):
    cfg = load_config()
    if profile not in cfg.get('remote_configs', {}):
        defaults = {item.key: getattr(item, 'default', "") if item.type != 'check' else False
                    for section in CONFIG_SCHEMA.values() for item in section}
        cfg.setdefault('remote_configs', {})[profile] = defaults
        save_config(cfg)
    return cfg

def build_base_args(profile, global_cfg, inferred_locks, local_path=""):
    """Translates state to CLI args. Dynamically maps absolute paths for Trash bins."""
    cfg = global_cfg.get('remote_configs', {}).get(profile, {})
    args = []
    
    active_state = cfg.copy()
    active_state.update(inferred_locks)
    
    import src.workbench_blueprint as blueprint
    import os

    for section in CONFIG_SCHEMA.values():
        for item in section:
            base_k = item.key
            flag = getattr(item, 'flag', None)
            if not flag: continue
            
            keys = [k for k in active_state if (k.split('__uid_')[0] if '__uid_' in k else k) == base_k]
            for k in keys:
                val = active_state.get(k)
                if val is None or val == "": 
                    if val != 0: continue
                
                # --- DYNAMIC TRASH PATH RESOLUTION ---
                if base_k == 'backup_path_1' and val == blueprint.TRASH_LOCAL_NAME:
                    val = os.path.join(local_path, blueprint.TRASH_LOCAL_NAME) if local_path else blueprint.TRASH_LOCAL_NAME
                elif base_k == 'backup_path_2' and val == blueprint.TRASH_CLOUD_NAME:
                    val = f"{profile}:{blueprint.TRASH_CLOUD_NAME}"
                # -------------------------------------
                
                t = getattr(item, 'type', None)
                if t == 'check' and val is True: 
                    args.append(flag)
                elif t in ('entry','combo'): 
                    args += [flag, str(val).strip()]
                elif t == 'multi':
                    cleaned = ",".join(p.strip() for p in str(val).split(',') if p.strip())
                    if cleaned: args += [flag, cleaned]
                elif t in ('stack','text'):
                    for line in [l.strip() for l in str(val).splitlines() if l.strip()]:
                        args += [flag, line]
                elif t == 'count':
                    try:
                        c = int(val)
                        if c > 0:
                            s = getattr(item,'short',None)
                            if s and s.startswith('-') and len(s) == 2:
                                args.append(f"-{s[1]*c}")
                            else:
                                args.extend([flag] * c)
                    except ValueError: pass
    return args