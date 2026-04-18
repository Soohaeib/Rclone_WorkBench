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

def evaluate_state(active_keys, active_values, item_lookup):
    """
    Derives values, locks, and disabled states based on active flags.
    Returns: (Final Keys, Enforced Values, Lock State Dict, Disabled/Rejected Dict)
    """
    f_keys = set(active_keys)
    f_vals = active_values.copy() # FIX: Start with the user's existing selections!
    l_keys = {} 
    d_keys = {} 
    
    loop_safety = 0
    changed = True

    while changed and loop_safety < 15:
        changed = False
        loop_safety += 1
        current_keys = list(f_keys)
        
        for key in current_keys:
            base = key.split('.')[0] if '.' in key else key
            item = item_lookup.get(base)
            if not item: continue

            # 1. REJECTS (Track globally to disable UI chips with the Owner's Label)
            for r in getattr(item, 'rejects', []):
                if r not in d_keys: d_keys[r] = item.label
                targets = [k for k in f_keys if (k.split('.')[0] if '.' in k else k) == r]
                for tr in targets:
                    f_keys.remove(tr)
                    if tr in f_vals: del f_vals[tr]
                    if tr in l_keys: del l_keys[tr]
                    changed = True

            # 2. EXPECTS (Auto-Equip)
            for e in getattr(item, 'expects', []):
                if not any((k.split('.')[0] if '.' in k else k) == e for k in f_keys):
                    f_keys.add(e); changed = True

            # 3. SATISFY (Value Enforcement & Smart Auto-Locking with Label Tracking)
            for tk, tv in getattr(item, 'satisfy', {}).items():
                if not any((k.split('.')[0] if '.' in k else k) == tk for k in f_keys):
                    f_keys.add(tk); changed = True
                
                if isinstance(tv, dict):
                    # Granular Lock (Multi-option)
                    current_str = str(f_vals.get(tk, ""))
                    opts = set(o.strip() for o in current_str.split(',') if o.strip())
                    
                    if tk not in l_keys or not isinstance(l_keys[tk], dict):
                        l_keys[tk] = {}
                        
                    local_changed = False
                    for sub_k, sub_v in tv.items():
                        if sub_v is True and sub_k not in opts: opts.add(sub_k); local_changed = True
                        elif sub_v is False and sub_k in opts: opts.remove(sub_k); local_changed = True
                        
                        # SMART AUTO-LOCK: Map the specific sub-option to the Owner's Label
                        if sub_k not in l_keys[tk]:
                            l_keys[tk][sub_k] = item.label
                            local_changed = True

                    if local_changed:
                        f_vals[tk] = ",".join(sorted(opts))
                        changed = True
                else:
                    # Full Macro Lock
                    if f_vals.get(tk) != tv:
                        f_vals[tk] = tv; changed = True
                    if l_keys.get(tk) != item.label:
                        l_keys[tk] = item.label; changed = True
                    
    return f_keys, f_vals, l_keys, d_keys

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