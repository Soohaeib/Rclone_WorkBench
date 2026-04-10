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
        cfg['remote_configs'][profile] = {i.key: getattr(i, 'default', "") if i.type != 'check' else False for sec in CONFIG_SCHEMA.values() for i in sec}
        save_config(cfg)
    return cfg

def build_base_args(profile, global_cfg, inferred_locks):
    cfg = global_cfg.get('remote_configs', {}).get(profile, {})
    args, state = [], {**cfg, **inferred_locks}

    for section in CONFIG_SCHEMA.values():
        for item in section:
            flag = getattr(item, 'flag', None)
            if not flag: continue
            
            for k in [x for x in state if (x.split('.')[0] if '.' in x else x) == item.key]:
                val = state.get(k)
                if not val and val != 0: continue
                
                t = getattr(item, 'type', None)
                if t == 'check' and val is True: args.append(flag)
                elif t in ('entry','combo'): args += [flag, str(val).strip()]
                elif t == 'multi' and (c := ",".join(p.strip() for p in str(val).split(',') if p.strip())): args += [flag, c]
                elif t in ('stack','text'): args += [x for line in str(val).splitlines() if line.strip() for x in (flag, line.strip())]
                elif t == 'count' and (c := int(val)) > 0:
                    s = getattr(item,'short',None)
                    args.append(f"-{s[1]*c}" if s and s.startswith('-') and len(s) == 2 else flag*c)
    return args