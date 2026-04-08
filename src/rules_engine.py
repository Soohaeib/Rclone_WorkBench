import src.workbench_blueprint as workbench_blueprint
import logging

def get_item_lookup():
    lookup = {}
    for cat in workbench_blueprint.SMART_SCHEMA.values():
        for i in cat: lookup[i.key] = i  
    for cat in workbench_blueprint.CONFIG_SCHEMA.values():
        for i in cat: lookup[i.key] = i  
    return lookup

def get_smart_keys():
    return {i.key for cat in workbench_blueprint.SMART_SCHEMA.values() for i in cat}

def validate_blueprint():
    lookup = get_item_lookup()
    errors = []
    for key, item in lookup.items():
        expects = getattr(item, 'expects', [])
        rejects = getattr(item, 'rejects', [])
        satisfy = getattr(item, 'satisfy', {})
        for e in expects:
            if e not in lookup: errors.append(f"[{key}] expects missing: '{e}'")
        for r in rejects:
            if r not in lookup: errors.append(f"[{key}] rejects missing: '{r}'")
        for s in satisfy.keys():
            if s not in lookup: errors.append(f"[{key}] satisfies missing: '{s}'")
    return errors

def evaluate_state(active_keys, item_lookup):
    final_keys = set(active_keys)
    forced_values = {}
    locked_keys = set()
    changed = True

    while changed:
        changed = False
        current_snapshot = list(final_keys)
        for key in current_snapshot:
            base_key = key.split('__uid_')[0] if '__uid_' in key else key
            item = item_lookup.get(base_key)
            if not item: continue

            # 1. Process Rejects
            for r in getattr(item, 'rejects', []):
                to_remove = [k for k in final_keys if (k.split('__uid_')[0] if '__uid_' in k else k) == r]
                for tr in to_remove:
                    final_keys.remove(tr)
                    changed = True

            # 2. Process Expects (Adds the base key only)
            for e in getattr(item, 'expects', []):
                if not any((k.split('__uid_')[0] if '__uid_' in k else k) == e for k in final_keys):
                    final_keys.add(e)
                    changed = True

            # 3. Process Satisfy
            for target_key, forced_val in getattr(item, 'satisfy', {}).items():
                if not any((k.split('__uid_')[0] if '__uid_' in k else k) == target_key for k in final_keys):
                    final_keys.add(target_key)
                    changed = True
                if forced_values.get(target_key) != forced_val:
                    forced_values[target_key] = forced_val
                    locked_keys.add(target_key)
                    changed = True
                    
    return final_keys, forced_values, locked_keys

def validate_state(live_state, item_lookup):
    errors = {}
    for key, val in live_state.items():
        base_key = key.split('__uid_')[0] if '__uid_' in key else key
        item = item_lookup.get(base_key)
        
        rules = getattr(item, 'validation', None)
        if not rules: continue
        
        if 'min' in rules:
            min_val = rules['min']
            if str(val).endswith('m') and min_val.endswith('m'):
                if int(str(val)[:-1]) < int(min_val[:-1]):
                    errors[key] = f"Value must be at least {min_val}"
    return errors