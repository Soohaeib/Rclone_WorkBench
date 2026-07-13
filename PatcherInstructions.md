# Smart Patcher Instruction Manual

## Overview
The `smart_patcher.py` script is a modular, context-aware utility designed to safely modify codebase files using JSON-based instruction files. It eliminates the need to manually write Python parsing logic for every update. By reading a structured JSON file, the patcher locates specific code snippets (anchors) and dynamically injects, replaces, or prepends new code (payloads).

---

## Core Features
* **JSON-Driven:** All modifications are declared in standard JSON files.
* **Context-Aware:** Uses exact string matching to find the correct location in a file without relying on fragile line numbers.
* **Idempotent / Safe:** Automatically checks if a payload has already been applied (for insertions) or if an anchor is missing, preventing duplicate code injection and file corruption.
* **Non-Destructive:** If an anchor is not found, the script skips that specific block rather than aborting the entire patching process.

---

## Usage

To apply a patch, execute the script from the terminal and pass the JSON file as an argument.

```bash
python3 smart_patcher.py update.json

```

> **Note:** If no JSON file is specified, the script will default to looking for `update.json` in the current directory.

---

## JSON Structure

The JSON file must contain a top-level array of objects. Each object represents a single file to be patched.

### File Object Schema

* **`file`** (String): The relative or absolute path to the file you want to modify.
* **`modifications`** (Array): A list of modification objects to apply to this specific file.

### Modification Object Schema

* **`action`** (String): The type of modification to perform. Must be one of the three supported actions listed below.
* **`anchor`** (String): The exact existing code snippet in the file that acts as the reference point. It should be unique enough to only match the intended location.
* **`payload`** (String): The new code or text to be injected or used as a replacement.

---

## Supported Actions

### 1. `replace`

Finds the exact **`anchor`** string and completely replaces it with the **`payload`** string.

```json
{
    "action": "replace",
    "anchor": "self.btn_stop.set_sensitive(False)",
    "payload": "self.btn_stop.set_sensitive(is_running)"
}

```

### 2. `insert_before`

Finds the **`anchor`** string and injects the **`payload`** directly on a new line above it.

```json
{
    "action": "insert_before",
    "anchor": "def stop_current_sync(self, btn):",
    "payload": "    # --- PROCESS KILL FUNCTIONS ---"
}

```

### 3. `insert_after`

Finds the **`anchor`** string and injects the **`payload`** directly on a new line below it.

```json
{
    "action": "insert_after",
    "anchor": "import os",
    "payload": "import datetime"
}

```

---

## Comprehensive Example (`update.json`)

```json
[
    {
        "file": "src/workbench_ui.py",
        "modifications": [
            {
                "action": "insert_after",
                "anchor": "import gi, os, subprocess",
                "payload": "import datetime"
            },
            {
                "action": "replace",
                "anchor": "self.btn_stop.set_sensitive(is_running)",
                "payload": "self.btn_stop.set_sensitive(is_running)\n        self.btn_stop.set_tooltip_text('Stop Active Sync Session')"
            },
            {
                "action": "insert_before",
                "anchor": "def stop_current_sync(self, btn):",
                "payload": "    # --- PROCESS KILL & TRASH FUNCTIONS ---"
            }
        ]
    }
]

```

## AI Agent Instructions

When generating patches for this application:

1. Always output modifications in a valid JSON format matching the schema above.
2. Ensure the **`anchor`** string is long enough to be unique within the target file. Include leading indentation spaces in the anchor if necessary to guarantee a unique match.
3. Include the necessary indentation in the **`payload`** to maintain the structural integrity of the target script (e.g., Python indentation).