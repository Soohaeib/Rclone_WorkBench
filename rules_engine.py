# rules_engine.py
from workbench_blueprint import SMART_SCHEMA, CONFIG_SCHEMA

def get_full_lookup():
    """Flattens all schema categories into a single searchable dictionary."""
    lookup = {item['key']: item for cat in SMART_SCHEMA.values() for item in cat}
    lookup.update({item['key']: item for cat in CONFIG_SCHEMA.values() for item in cat})
    return lookup

def evaluate_canvas(active_keys):
    """
    Resolves dependencies (expects) and conflicts (rejects).
    Returns (final_keys, forced_values, locked_keys).
    """
    lookup = get_full_lookup()
    final_keys = set(active_keys)
    forced_values = {}
    locked_keys = set()

    changed = True
    while changed:
        changed = False
        for key in list(final_keys):
            item = lookup.get(key)
            if not item: continue

            # Resolve Conflicts
            for r in item.get('rejects', []):
                if r in final_keys:
                    final_keys.remove(r)
                    changed = True

            # Resolve Prerequisites
            for e in item.get('expects', []):
                if e not in final_keys:
                    final_keys.add(e)
                    changed = True

            # Apply Forced Values (Satisfy)
            for s_key, s_val in item.get('satisfy', {}).items():
                forced_values[s_key] = s_val
                locked_keys.add(s_key)
                
    return final_keys, forced_values, locked_keys