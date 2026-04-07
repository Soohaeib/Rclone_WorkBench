import src.workbench_blueprint as workbench_blueprint
import logging
from dataclasses import asdict

def get_item_lookup():
    """Returns a fast object lookup (removes asdict to keep dot notation)."""
    lookup = {}
    for cat in workbench_blueprint.SMART_SCHEMA.values():
        for i in cat: lookup[i.key] = i  # Store the object, not a dict
    for cat in workbench_blueprint.CONFIG_SCHEMA.values():
        for i in cat: lookup[i.key] = i  # Store the object, not a dict
    return lookup

def get_smart_keys():
    """Returns a set of keys strictly belonging to Smart Presets."""
    return {i.key for cat in workbench_blueprint.SMART_SCHEMA.values() for i in cat}

def validate_blueprint():
    lookup = get_item_lookup()
    errors = []
    for key, item in lookup.items():
        # Use getattr to safely check for attributes that might not exist on all types
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
    """Refined to use dot notation safely."""
    final_keys = set(active_keys)
    forced_values = {}
    locked_keys = set()
    changed = True

    while changed:
        changed = False
        current_snapshot = list(final_keys)
        for key in current_snapshot:
            item = item_lookup.get(key)
            if not item: continue

            # 1. Process Rejects
            for r in getattr(item, 'rejects', []):
                if r in final_keys:
                    final_keys.remove(r)
                    changed = True

            # 2. Process Expects
            for e in getattr(item, 'expects', []):
                if e not in final_keys:
                    final_keys.add(e)
                    changed = True

            # 3. Process Satisfy
            for target_key, forced_val in getattr(item, 'satisfy', {}).items():
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
        
        # FIX: Use getattr to safely fetch the 'validation' dictionary from the dataclass object
        rules = getattr(item, 'validation', None)
        if not rules:
            continue
        
        # Example validation: minimum duration for time-based entries
        if 'min' in rules:
            min_val = rules['min']
            # Basic string matching for duration formats (e.g., '2m')
            # In a production app, parse the duration properly here
            if str(val).endswith('m') and min_val.endswith('m'):
                if int(str(val)[:-1]) < int(min_val[:-1]):
                    errors[key] = f"Value must be at least {min_val}"
                    
    return errors