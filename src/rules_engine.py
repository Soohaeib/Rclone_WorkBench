from src.workbench_blueprint import CONFIG_SCHEMA, SMART_SCHEMA

def get_item_lookup():
    return {i.key: i for schema in (SMART_SCHEMA, CONFIG_SCHEMA) for cat in schema.values() for i in cat}

def get_smart_keys():
    return {i.key for cat in SMART_SCHEMA.values() for i in cat}

def validate_blueprint():
    lookup = get_item_lookup()
    errors = []
    for k, i in lookup.items():
        if any(e not in lookup for e in getattr(i, 'expects', [])): errors.append(f"[{k}] missing expected key")
        if any(r not in lookup for r in getattr(i, 'rejects', [])): errors.append(f"[{k}] missing rejected key")
        if any(s not in lookup for s in getattr(i, 'satisfy', {})): errors.append(f"[{k}] missing satisfied key")
    return errors

def evaluate_state(active_keys, item_lookup):
    f_keys, f_vals, l_keys, changed = set(active_keys), {}, set(), True

    while changed:
        changed = False
        for key in list(f_keys):
            base = key.split('.')[0] if '.' in key else key
            item = item_lookup.get(base)
            if not item: continue

            # Rejects
            for r in getattr(item, 'rejects', []):
                for tr in [k for k in f_keys if (k.split('.')[0] if '.' in k else k) == r]:
                    f_keys.remove(tr); changed = True

            # Expects & Satisfy
            for e in getattr(item, 'expects', []):
                if not any((k.split('.')[0] if '.' in k else k) == e for k in f_keys):
                    f_keys.add(e); changed = True

            for tk, tv in getattr(item, 'satisfy', {}).items():
                if not any((k.split('.')[0] if '.' in k else k) == tk for k in f_keys):
                    f_keys.add(tk); changed = True
                if f_vals.get(tk) != tv:
                    f_vals[tk] = tv; l_keys.add(tk); changed = True
                    
    return f_keys, f_vals, l_keys

def validate_state(live_state, lookup):
    return {k: f"Must be at least {lookup[k.split('.')[0] if '.' in k else k].validation['min']}" 
            for k, v in live_state.items() 
            if getattr(lookup.get(k.split('.')[0] if '.' in k else k), 'validation', {}).get('min', '').endswith('m') 
            and str(v).endswith('m') and int(str(v)[:-1]) < int(lookup[k.split('.')[0] if '.' in k else k].validation['min'][:-1])}