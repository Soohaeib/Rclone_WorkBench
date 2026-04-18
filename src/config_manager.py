import os, json
from src.workbench_blueprint import APP_DIR, JSON_CONFIG_FILE, CONFIG_SCHEMA

def load_config():
    try:
        with open(JSON_CONFIG_FILE, 'r') as f: return json.load(f)
    except: return {"local_paths": {}, "remote_configs": {}}

def save_config(cfg):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(JSON_CONFIG_FILE, 'w') as f: json.dump(cfg, f, indent=4)

def ensure_profile_exists(profile):
    cfg = load_config()
    if profile not in cfg.setdefault('remote_configs', {}):
        cfg['remote_configs'][profile] = {getattr(i, 'flag', ''): getattr(i, 'default', "") if i.type != 'check' else False for sec in CONFIG_SCHEMA.values() for i in sec}
        save_config(cfg)
    return cfg

def build_base_args(profile, global_cfg, inferred_locks):
    cfg = global_cfg.get('remote_configs', {}).get(profile, {})
    args, state = [], {**cfg, **inferred_locks}

    for section in CONFIG_SCHEMA.values():
        for item in section:
            flag = getattr(item, 'flag', None)
            if not flag: continue
            
            cmd_flag = getattr(item, 'short', None) or flag
            
            for k in [x for x in state if (x.split('.')[0] if '.' in x else x) == flag]:
                val = state.get(k)
                if not val and val != 0: continue
                
                t = getattr(item, 'type', None)
                
                if t == 'check' and val is True: 
                    args.append(cmd_flag)
                elif t == 'multi' and (c := ",".join(p.strip() for p in str(val).split(',') if p.strip())): 
                    args += [cmd_flag, c]
                elif t == 'combo' and str(val).strip(): 
                    args += [cmd_flag, str(val).strip()]
                elif t == 'text': 
                    args += [x for line in str(val).splitlines() if line.strip() for x in (cmd_flag, line.strip())]
                elif t == 'entry' and str(val).strip():
                    args += [cmd_flag, str(val).strip()]
                elif t == 'number' and int(val) > 0: 
                    unit = getattr(item, 'unit', '')
                    args += [cmd_flag, f"{val}{unit}"]
                elif t == 'count' and int(val) > 0:
                    args.extend([cmd_flag] * int(val))
                    
    return args