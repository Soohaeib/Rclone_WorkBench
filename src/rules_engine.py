from src.workbench_blueprint import CONFIG_SCHEMA, SMART_SCHEMA

def get_item_lookup():
    return {getattr(i, 'flag', getattr(i, 'id', '')): i for schema in (SMART_SCHEMA, CONFIG_SCHEMA) for cat in schema.values() for i in cat}

def get_smart_keys():
    return {i.id for cat in SMART_SCHEMA.values() for i in cat}

def validate_blueprint():
    lookup = get_item_lookup()
    errors = []
    for k, i in lookup.items():
        if any(e not in lookup for e in getattr(i, 'expects', [])): errors.append(f"[{k}] missing expected key")
        if any(r not in lookup for r in getattr(i, 'rejects', [])): errors.append(f"[{k}] missing rejected key")
        if any(s not in lookup for s in getattr(i, 'satisfy', {})): errors.append(f"[{k}] missing satisfied key")
    return errors

def evaluate_state(active_keys, item_lookup):
    f_keys, f_vals, l_keys, changed = set(active_keys), {}, {}, True

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

            # Expects
            for e in getattr(item, 'expects', []):
                if not any((k.split('.')[0] if '.' in k else k) == e for k in f_keys):
                    f_keys.add(e); changed = True

            # Satisfy (Deep Merge & Micro-Locking)
            for tk, tv in getattr(item, 'satisfy', {}).items():
                if not any((k.split('.')[0] if '.' in k else k) == tk for k in f_keys):
                    f_keys.add(tk); changed = True
                
                if isinstance(tv, dict):
                    current_val = str(f_vals.get(tk, ""))
                    opts = [o.strip() for o in current_val.split(',')] if current_val else []
                    current_locks = l_keys.get(tk, [])
                    locks = True if current_locks is True else current_locks.copy()
                    
                    for sub_k, sub_v in tv.items():
                        if sub_k == 'lock':
                            if isinstance(locks, list):
                                for l in sub_v:
                                    if l not in locks: locks.append(l); changed = True
                        elif sub_v is True and sub_k not in opts:
                            opts.append(sub_k); changed = True
                        elif sub_v is False and sub_k in opts:
                            opts.remove(sub_k); changed = True
                            
                    new_val = ",".join(opts)
                    if str(f_vals.get(tk, "")) != new_val:
                        f_vals[tk] = new_val; changed = True
                    
                    if isinstance(locks, list) and locks and l_keys.get(tk) != locks:
                        l_keys[tk] = locks; changed = True
                else:
                    if f_vals.get(tk) != tv:
                        f_vals[tk] = tv; changed = True
                    if l_keys.get(tk) is not True:
                        l_keys[tk] = True; changed = True
                    
    return f_keys, f_vals, l_keys

def validate_state(live_state, lookup):
    errors = {}
    for k, v in live_state.items():
        if k.startswith('_AUDIT_ERROR'):
            clean_key = k.replace('_AUDIT_ERROR_', 'Audit Failure (') + ')'
            errors[clean_key] = str(v)
            
    for k, v in live_state.items():
        base_key = k.split('.')[0] if '.' in k else k
        item = lookup.get(base_key)
        if not item or not getattr(item, 'validation', None): continue
        
        rules = item.validation
        if isinstance(rules, dict):
            try:
                num_v = float(v)
                if 'min' in rules and num_v < rules['min']:
                    errors[k] = f"Value {v} is below minimum of {rules['min']}."
                if 'max' in rules and num_v > rules['max']:
                    errors[k] = f"Value {v} is above maximum of {rules['max']}."
            except (ValueError, TypeError):
                pass
                
    return errors