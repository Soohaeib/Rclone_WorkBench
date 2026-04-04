import src.workbench_blueprint as workbench_blueprint
import logging

def get_item_lookup():
    """Flattens SMART_SCHEMA and CONFIG_SCHEMA into a fast dictionary lookup."""
    lookup = {}
    for cat in workbench_blueprint.SMART_SCHEMA.values():
        for i in cat: lookup[i['key']] = i
    for cat in workbench_blueprint.CONFIG_SCHEMA.values():
        for i in cat: lookup[i['key']] = i
    return lookup

def get_smart_keys():
    """Returns a set of keys strictly belonging to Smart Presets."""
    return {i['key'] for cat in workbench_blueprint.SMART_SCHEMA.values() for i in cat}

def validate_blueprint():
    """
    Schema Linter: Checks for missing keys in expects, rejects, and satisfy arrays.
    Prevents 'Ghost Dependencies' before the app runs.
    """
    lookup = get_item_lookup()
    errors = []
    for key, item in lookup.items():
        for e in item.get('expects', []):
            if e not in lookup: errors.append(f"[{key}] expects missing key: '{e}'")
        for r in item.get('rejects', []):
            if r not in lookup: errors.append(f"[{key}] rejects missing key: '{r}'")
        for s in item.get('satisfy', {}).keys():
            if s not in lookup: errors.append(f"[{key}] satisfies missing key: '{s}'")
    
    if errors:
        error_msg = "Blueprint Validation Failed (Ghost Dependencies):\n" + "\n".join(errors)
        logging.error(error_msg)
        raise ValueError(error_msg)
    return True

def evaluate_state(active_keys, item_lookup):
    """
    Evaluates the current active keys against expects, rejects, and satisfy rules.
    Returns: (resolved_keys_set, forced_values_dict, locked_keys_set)
    """
    final_keys = set(active_keys)
    forced_values = {}
    locked_keys = set()

    changed = True
    iterations = 0
    MAX_ITERATIONS = 50 # Logic Guard against Circular Dependencies

    while changed:
        if iterations > MAX_ITERATIONS:
            logging.error("Circular dependency detected in Rules Engine. Breaking loop to prevent UI freeze.")
            break
        
        iterations += 1
        changed = False
        
        for key in list(final_keys):
            item = item_lookup.get(key)
            if not item: continue

            # 1. Process Rejects (Conflicts)
            for r in item.get('rejects', []):
                if r in final_keys:
                    final_keys.remove(r)
                    changed = True

            # 2. Process Expects (Prerequisites)
            for e in item.get('expects', []):
                if e not in final_keys:
                    final_keys.add(e)
                    changed = True

            # 3. Process Satisfy (Value Enforcement)
            for target_key, forced_val in item.get('satisfy', {}).items():
                if target_key not in final_keys:
                    final_keys.add(target_key)
                    changed = True
                
                if forced_values.get(target_key) != forced_val:
                    forced_values[target_key] = forced_val
                    locked_keys.add(target_key)
                    changed = True

    return final_keys, forced_values, locked_keys

def validate_state(live_state, item_lookup):
    """
    Validates the generated command values against schema constraints before execution.
    Returns a dictionary of error messages {key: error_string}.
    """
    errors = {}
    for key, val in live_state.items():
        item = item_lookup.get(key)
        if not item or 'validation' not in item:
            continue
        
        rules = item['validation']
        
        # Example constraint: Minimum duration check (e.g., '2m')
        if 'min' in rules:
            min_val = rules['min']
            if str(val).endswith('m') and min_val.endswith('m'):
                if int(str(val)[:-1]) < int(min_val[:-1]):
                    errors[key] = f"Value must be at least {min_val}"
                    
    return errors