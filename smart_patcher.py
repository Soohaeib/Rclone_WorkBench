import os
import sys
import json

def apply_patches(json_path):
    if not os.path.exists(json_path):
        print(f"[X] Error: Could not find patch file '{json_path}'.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        try:
            patch_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[X] Error parsing JSON: {e}")
            return

    print(f"=== Beginning Smart Patching from {json_path} ===")

    for file_patch in patch_data:
        filepath = file_patch.get("file")
        modifications = file_patch.get("modifications", [])

        if not os.path.exists(filepath):
            print(f"[-] Warning: Target file '{filepath}' not found. Skipping.")
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        patched_content = content
        changes_made = False

        for mod in modifications:
            action = mod.get("action", "replace")
            anchor = mod.get("anchor", "")
            payload = mod.get("payload", "")

            # Idempotency check: Skip if the exact payload is already in the file (useful for insertions)
            if action in ["insert_before", "insert_after"] and payload in patched_content:
                print(f"  [!] Skipping {action}: Payload already exists in '{filepath}'.")
                continue

            if anchor not in patched_content:
                # If replacing, maybe it was already replaced
                if action == "replace" and payload in patched_content:
                    print(f"  [!] Skipping replace: Payload already seems applied in '{filepath}'.")
                else:
                    print(f"  [X] Anchor not found in '{filepath}'. Skipping this block.")
                continue

            # Apply the requested action contextually
            if action == "replace":
                patched_content = patched_content.replace(anchor, payload)
            elif action == "insert_before":
                patched_content = patched_content.replace(anchor, payload + "\n" + anchor)
            elif action == "insert_after":
                patched_content = patched_content.replace(anchor, anchor + "\n" + payload)

            changes_made = True

        # Write back only if modifications were successfully made
        if changes_made and patched_content != content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(patched_content)
            print(f"[✓] Successfully patched: '{filepath}'")
        else:
            print(f"[!] No new changes were needed for '{filepath}'.")

    print("=== Patching Complete! ===")

if __name__ == "__main__":
    # Allow passing a specific JSON file, default to 'update.json'
    target_json = sys.argv[1] if len(sys.argv) > 1 else "update.json"
    apply_patches(target_json)