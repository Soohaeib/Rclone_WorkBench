import os
import json
from src.workbench_blueprint import APP_DIR, JSON_CONFIG_FILE, CONFIG_SCHEMA

def load_config():
    """Loads the central JSON configuration file."""
    if not os.path.exists(JSON_CONFIG_FILE):
        return {"local_paths": {}, "remote_configs": {}}
    try:
        with open(JSON_CONFIG_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"local_paths": {}, "remote_configs": {}}

def save_config(cfg):
    """Saves the current state to disk."""
    os.makedirs(APP_DIR, exist_ok=True)
    with open(JSON_CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=4)

def ensure_profile_exists(profile):
    """Initializes a profile with default values from the Blueprint if it doesn't exist."""
    cfg = load_config()
    if profile not in cfg.get('remote_configs', {}):
        defaults = {}
        for section in CONFIG_SCHEMA.values():
            for item in section:
                # Use default value if provided, or empty string/False based on type
                val = item.get('default', "") if item['type'] != 'check' else False
                defaults[item['key']] = val
        
        cfg.setdefault('remote_configs', {})[profile] = defaults
        save_config(cfg)
    return cfg

def build_base_args(profile, global_cfg, inferred_locks):
    """
    Translates the UI state (and any logic overrides) into Rclone flags.
    inferred_locks: values forced by the Rules Engine (e.g., 'satisfy' rules).
    """
    profile_cfg = global_cfg.get('remote_configs', {}).get(profile, {})
    args = []
    
    for section in CONFIG_SCHEMA.values():
        for item in section:
            key, flag = item['key'], item.get('flag')
            if not flag: 
                continue # Skips internal UI keys that don't have rclone flags
            
            # Priority: 1. Rules Engine Overrides (inferred_locks) 2. Saved Config
            val = inferred_locks.get(key) if key in inferred_locks else profile_cfg.get(key)
            if not val: 
                continue
            
            # Type-specific flag construction
            if item['type'] == 'check' and val is True:
                args.append(flag)
            elif item['type'] in ['entry', 'combo']:
                args.extend([flag, str(val).strip()])
            elif item['type'] == 'multi':
                # For flags like --compare size,modtime
                cleaned = ",".join([p.strip() for p in val.split(',') if p.strip()])
                if cleaned: args.extend([flag, cleaned])
            elif item['type'] == 'stack':
                # For repetitive flags like --filter
                lines = [line.strip() for line in str(val).split('\n') if line.strip()]
                for line in lines:
                    args.extend([flag, line])
                    
    return args