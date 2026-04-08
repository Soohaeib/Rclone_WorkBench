import os, json
from src.workbench_blueprint import APP_DIR, JSON_CONFIG_FILE

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
    import src.workbench_blueprint as blueprint
    cfg = load_config()
    if profile not in cfg.get('remote_configs', {}):
        defaults = {item.key: getattr(item, 'default', "") if item.type != 'check' else False
                    for section in blueprint.CONFIG_SCHEMA.values() for item in section}
        cfg.setdefault('remote_configs', {})[profile] = defaults
        save_config(cfg)
    return cfg

def build_base_args(profile, global_cfg, inferred_locks):
    cfg = global_cfg.get('remote_configs', {}).get(profile, {})
    args = []
    import src.workbench_blueprint as blueprint
    active_state = {**cfg, **inferred_locks}
    for section in blueprint.CONFIG_SCHEMA.values():
        for item in section:
            flag = getattr(item, 'flag', None)
            if not flag: continue
            base_k = item.key
            keys = [k for k in active_state if (k.split('__uid_')[0] if '__uid_' in k else k) == base_k]
            for k in keys:
                val = active_state.get(k)
                if not val: continue
                t = getattr(item, 'type', None)
                if t == 'check' and val is True: args.append(flag)
                elif t in ('entry','combo'): args += [flag, str(val).strip()]
                elif t == 'multi':
                    cleaned = ",".join(p.strip() for p in str(val).split(',') if p.strip())
                    if cleaned: args += [flag, cleaned]
                elif t in ('stack','text'):
                    for line in [l.strip() for l in str(val).splitlines() if l.strip()]:
                        args += [flag, line]
                elif t == 'count':
                    try:
                        c = int(val)
                        if c>0:
                            s = getattr(item,'short',None)
                            args.append(f"-{s[1]*c}" if s and s.startswith('-') and len(s)==2 else flag*c)
                    except: pass
    return args
