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
                val = item.get('default', "") if item['type'] != 'check' else False
                defaults[item['key']] = val
        
        cfg.setdefault('remote_configs', {})[profile] = defaults
        save_config(cfg)
    return cfg

def build_base_args(profile, global_cfg, inferred_locks):
    cfg = global_cfg.get('remote_configs', {}).get(profile, {})
    args = []
    
    # Use blueprint (so ensure you have 'import src.workbench_blueprint as blueprint' at the top)
    import src.workbench_blueprint as blueprint
    
    for section in blueprint.CONFIG_SCHEMA.values():
        for item in section:
            # FIX: Use dot notation here
            k = item.key
            flag = getattr(item, 'flag', None)
            
            if not flag: continue # Skips Smart Presets automatically
            
            val = inferred_locks.get(k) if k in inferred_locks else cfg.get(k)
            if not val: continue
            
            # FIX: Use dot notation for type checking
            if item.type == 'check' and val is True:
                args.append(flag)
            elif item.type in ['entry', 'combo']:
                args.extend([flag, str(val).strip()])
            elif item.type == 'multi':
                cleaned = ",".join([p.strip() for p in val.split(',') if p.strip()])
                if cleaned: args.extend([flag, cleaned])
            elif item.type == 'stack':
                lines = [line.strip() for line in str(val).split('\n') if line.strip()]
                for line in lines:
                    args.extend([flag, line])
                    
    return args