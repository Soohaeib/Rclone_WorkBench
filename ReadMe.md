# The Workbench: A Linux Tray App for Rclone Bisync Management
This application uses a gamified, inventory-based framework for managing rclone bisync operations.

## System Architecture
The Workbench operates as a multi-layered ecosystem where data, logic, and execution are strictly decoupled:

  - `workbench_blueprint.py`: __The Data Authority__. Contains the `CONFIG_SCHEMA` (tools) and `SMART_SCHEMA` (procedures). It is the sole source of truth for card definitions.
  - `rules_engine.py`: __The Logic Processor__. Evaluates card relationships (`expects`, `rejects`, `satisfy`) and enforces validation to ensure a valid command state.
  - `smart_automations.py`: __The Heuristic Scanner__. Checks the local environment (e.g., scanning for `.lst` files in `~/.cache/rclone/bisync`) to recommend relevant Smart Presets.
  - `smart_logic_hooks.py`: __The Orchestrator__. Contains Python methods triggered by a preset's `python_hook`. It handles complex tasks like session normalization or creating safety sentinel files.
  - `rclone_runner.py`: __The Backend Executor__. Manages the subprocess calls to rclone bisync, captures exit codes, and pipes raw JSONL output to the logs.
  - `log_formatter.py`: __The Parser__. Translates raw rclone JSONL logs into human-readable actions for the UI.
  - `config_manager.py`: __The Persistence Layer__. Handles the loading and saving of bisync_settings.json and ensures profile integrity.
  - `main_tray.py` / `app.py`: __The Main Controller__. Manages the application lifecycle, system tray integration, and cross-module communication.
  - `workbench_ui.py`: __The Canvas__. The GTK3 interface where users interact with the Inventory, Smart Presets, and the command Canvas

## Anatomy of a Smart Preset
Procedures in `SMART_SCHEMA` are __Master Keys__ that orchestrate the application's behavior across multiple modules.
```json
{
  "label": "Human Readable Procedure",
  "key": "preset_unique_key",
  "trigger_condition": "manual_toggle",
  "auto_apply": false,
  "lifecycle": "persistent",
  "python_hook": "logic_method_name",
  "color": "#HEXCODE",
  "desc": "Strategy explanation",

  "expects": ["key1"],
  "satisfy": {"key1": "value"},
  "rejects": ["key2"]
}
```
### Key descriptions

  - `label` — The name of the procedure shown in the `workbench_ui.py` Smart Presets panel.
  - `key` — Unique identifier used by the `rules_engine.py` to resolve dependencies.
  - `trigger_condition` — Environmental state monitored by `smart_automations.py` (e.g., missing_listing_file). If the condition is met, the UI suggests this preset.
  - `auto_apply` — __Boolean__. If `True`, the system applies the payload via `rules_engine.py` automatically; if false, `workbench_ui.py` prompts the user.
  - `lifecycle` — Defines the persistence of the preset.
    - `one_time`: Preset is "dropped" by the logic engine after `rclone_runner.py` reports a successful `exit 0`.
    - `persistent`: Preset remains active across all sessions managed by `config_manager.py`.
  - `python_hook` — Points to a method in `smart_logic_hooks.py` to perform actions CLI flags cannot (e.g., renaming `.lst` state files to normalize session names).
  - `color` — Hex color used by `workbench_ui.py` for visual categorization in the three-panel layout.
  - `desc` — Explanation of the technical strategy (e.g., "Safe Trash Protection").

Preset Orchestration Keys

  - `expects` — List of cards `rules_engine.py` must pull onto the Canvas
  - `satisfy` — Map of `{key: value}` used to Lock flags to safe values (e.g., forcing `--max-lock 2m`).
  - `rejects` — List of cards `rules_engine.py` must drop to prevent logical conflicts on the command line.

### Strategic Preset Examples

- **The "Unattended Resilience" Kit**:
    - **Logic**: Uses `satisfy` to enable the "Golden Combo" of `--resilient`, `--recover`, and `--conflict-resolve newer`.
    - **Value**: Specifically optimized for background automation (such as `cron` or `systemd` timers) to self-heal from interruptions and automatically expire stale locks without requiring human intervention or a manual resync.
- **The "Safe Resync" Trigger**:
    - **Logic**: Sets `lifecycle` to `one_time` and uses `satisfy` to force `{ "resync": true, "resync_mode": "newer" }`.
    - **Value**: Acts as a "reset button" to rebuild synchronization state knowledge from scratch when filesystems have drifted or the state directory is lost. The `one_time` lifecycle is a critical guard against the __"Ghost File" phenomenon__, where habitual resyncing nullifies deletion detection and causes previously deleted files to keep reappearing from the opposite path.
- **The "Hub-and-Spoke" Spoke Kit**:
    - **Logic**: Uses `satisfy` to enforce a low `--max-delete` threshold (e.g., 5%) and enables `--check-access` using an `RCLONE_TEST` sentinel.
    - **Value**:  Provides essential protective circuit breakers for "spoke" devices participating in a __Star Topology__ multi-device setup. It ensures the central "Hub" remains uncorrupted by aborting the sync if a spoke's network drive unmounts or if an unexpected filesystem failure triggers a mass deletion event.

## Anatomy of an Inventory Item

Each card in `CONFIG_SCHEMA` is a JSON dictionary with the following keys. Newer keys used by the schema are documented here so integrators and UI engineers can implement the rules engine correctly.
```json
{
  "label": "Human Readable Name",
  "key": "unique_json_key",
  "type": "check",
  "flag": "--rclone-flag",
  "short": "-n",
  "default": false,
  "default_equipped": true,
  "color": "#HEXCODE",
  "desc": "Short description",

  "rejects": ["key1", "key2"],
  "expects": ["key3"],
  "satisfy": {"key3": "value"},
  "validation": {"min": "2m"},
  "options": ["val1", "val2"]
}
```

### Key descriptions

- `label` — Human readable title shown on the card.
- `key` — Unique identifier used for JSON storage and rule references. Must be unique.
- `type` — One of the supported card types (see Inventory Types).
- `flag` — The actual rclone CLI flag emitted when the card is equipped.
- `short` — Optional shorthand notation for the flag (for example `-n` for `--dry-run`). The UI may display the shorthand and the command generator may prefer it for compact command lines.
- `default` — Default string value for entry-like cards.
- `default_equipped` — __Boolean__. If `True`, the card loads onto the Canvas at startup as part of the __Safe Baseline__. These pre-loaded cards (such as `dry_run`, `check_sync`, and `resilient`) ensure the application starts in a non-destructive, resilient state.
- `color` — Optional hex color for the card header.
- `desc` — Short explanatory text shown on the card.

### Rules engine keys

- `rejects` — List of other card keys that must be automatically dropped from the Canvas when this card is equipped. Use this to enforce __mutual exclusion__ (e.g., selecting one delete mode drops all others).
- `expects` — List of other card keys that must be automatically pulled onto the Canvas when this card is equipped. Use this to enforce prerequisites.
- `satisfy` — Map of `{key: value}` used to force a dependent card to a specific value when this card is equipped (e.g., a "Quick Check" preset sets `transfers` to `16`).
- `validation` — Dictionary of constraints the UI and backend must enforce. Example: `{"min":"2m"}` for `max_lock` to ensure stale locks can safely expire. Validation must be enforced both client-side and server-side.
- `options` — Required for __combo__ cards; the allowed dropdown values.

### Inventory Types

The UI must support these card types and render them appropriately:

- `check` — A toggle-style card. When equipped it emits the flag with no value (e.g., `--resync`).
- `entry` — A single text input. When equipped it emits `--flag "value"`.
- `combo` — A dropdown selector for a single predefined value.
- `multi` — A set of independent checkboxes that combine into a comma-separated value for the flag (e.g., `--compare "size,modtime"`).
- `stack` — A multiline text field used for rules like -`-filter` where each line is meaningful to create `-- flag --flagX value1 (= + or - with string) --flagX value2` sidewise multiple times.
- `count` — A repeatable counter (e.g., `-v`, `-vv`). UI renders `+`/`-` controls; generator emits __repeated shorthand flags__ (e.g., `-v` × 3 → `-vvv`).
- `entry_array` — Accepts multiple independent strings (e.g., multiple `--exclude` values). The UI must allow adding/removing entries, and the generator should emit __repeated flags__ for each entry.

### Rule Interaction Examples
These examples demonstrate how the Rules Engine ensures a valid command state within the Workbench UI by processing dependencies and constraints in a recursive cascade.

- #### Mutually Exclusive Scenario using `rejects`
  The `rejects` key enforces mutual exclusion to prevent conflicting command-line states.
  ```json
  {"label":"Delete After","key":"delete_after","type":"check","flag":"--delete-after","rejects":["delete_before","delete_during"]},
  {"label":"Delete Before","key":"delete_before","type":"check","flag":"--delete-before","rejects":["delete_after","delete_during"]},
  {"label":"Delete During","key":"delete_during","type":"check","flag":"--delete-during","rejects":["delete_after","delete_before"]}
  ```
  __Behavior__: Equipping any one of these cards will automatically drop the other two from the Canvas, ensuring only one sync-delete strategy is active at any time.
  __Compare Mode Example__: Equipping the `compare_mode` (a `multi` card) will reject standalone checksum and `size_only` checkboxes. The UI must visually disable or remove these standalone cards when `compare_mode` is active to prevent logical redundancy.

- #### Prerequisite Scenario using `expects`
  The `expects` key defines prerequisites that must be active for a specific flag to function correctly.
  ```json
  {"label":"Force Full Resync","key":"resync","type":"check","flag":"--resync", "default_equipped": false},
  {"label":"Resync Mode","key":"resync_mode","type":"combo","flag":"--resync-mode","options":["path1","path2","newer","older"],"expects":["resync"]}
  ```
  __Behavior__: Equipping `resync_mode` automatically pulls the base `resync` card onto the Canvas. If the prerequisite (`resync`) cannot be equipped due to validation or safety policy, the UI must prevent the user from equipping `resync_mode`.
  __Track Renames Example__: The `track_renames_strategy` card includes `"expects":["track_renames"]` so a specific strategy cannot be selected without first enabling the rename tracking engine.

- #### Value Enforcer using `satisfy`
  The `satisfy` key allows a card (or a __Smart Preset__) to force a specific value onto another card, effectively "locking" it for safety.
  ```json
  {
    "label":"Quick Check",
    "key":"q_check",
    "type":"check",
    "flag":"--fast-list",
    "expects":["transfers"],
    "satisfy":{"transfers":"16"}
  }
  ```
  __Behavior__: Equipping `q_check` pulls `transfers` onto the Canvas and automatically sets its value to `16`. When a value is "satisfied" by another card, the UI should visually lock the target widget so the user cannot manually override the enforced safety logic.

### Practical Rules for Hashing and Optimization
Flags that alter checksum behavior must include `expects` entries requiring an active checksum-based comparison.
```json
{"label":"Slow Hash Sync Only","key":"slow_hash_sync_only","type":"check","flag":"--slow-hash-sync-only","expects":["checksum","compare_mode"]}
```
__Behavior__: This prevents equipping ineffective options, such as `--slow-hash-sync-only`, unless either the standalone `checksum` card is equipped or the `compare_mode` multi-select includes `checksum`.

### Validation and Constraints
Validation objects are enforced by the UI and the backend (`config_manager.py`) to ensure all values meet rclone's technical minimums.
```json
{"label":"Max Lock","key":"max_lock","type":"entry","flag":"--max-lock","default":"2m","validation":{"min":"2m"}}
```
__Behavior__: The UI must prevent users from entering durations below the 2m minimum. This ensures that stale `.lck` files can safely expire, allowing automated background runs to self-recover from prior crashes.

### Reset Defaults
The __Reset Defaults__ button restores the Canvas to match the strict `default_equipped` booleans defined in the `CONFIG_SCHEMA`.
__Behavior__: This action removes all manual overrides and re-applies the logic cascade (`rejects` -> `expects` -> `satisfy`) to return the Canvas to the Safe Baseline (e.g., `dry_run`, `check_sync`, and `resilient` pre-loaded)

## Quick implementation notes for integrators
To ensure the Workbench remains functional, minimal, and safe, integrators must adhere to the following logic requirements:

- __Recursive Rules Cascade__: Every card toggle must trigger a re-evaluation of the entire state in a single cascade: __Rejects__ (drop conflicts) -> __Expects__ (pull prerequisites) -> __Satisfy__ (force values) -> __Validate__ (check constraints).

- __Visual State Feedback__:
  - __Locking__: If a card is "satisfied" by an active __Smart Preset__, the UI must visually dim or disable its controls to show it is under automated management.
  - __Validation__: Enforce constraints both client-side (immediate widget feedback) and server-side (`config_manager.py`) to prevent invalid states like `--max-lock` falling below __2m__.

- __One-Time Lifecycle Management__: For presets with `lifecycle: one_time` (e.g., `--resync` triggers), the Rules Engine must monitor the exit status from `rclone_runner.py`. The preset and its dependent flags must be automatically dropped from the Canvas only after a successful `exit 0` to prevent the "Ghost File" phenomenon.
- __Orchestration via Python Hooks__: When a preset contains a `python_hook`, the backend must execute the corresponding method in `smart_logic_hooks.py` before or after the main rclone process. This is mandatory for:
  - __Session Normalization__: Renaming `.lst` files to match suffixes (e.g., `{suffix}`) added by backend-specific flags.
  - __Sentinel Creation__: Using `rclone touch` to ensure `RCLONE_TEST` files exist for `--check-access`.

- __Command Line Generation__:
  - `type: count`: Convert the intensity integer into repeated shorthand flags (e.g., `-v` × 3 → `-vvv`).
  - `type: entry_array` __and__ `stack`: Emit repeated long flags for each independent line or entry (e.g., `--exclude "a" --exclude "b"`).
  - __Preference__: Prefer shorthand flags (e.g., `-n`) for UI display and generated commands to keep logs compact.

## Example snippets

### `compare_mode` rejecting standalone flags
Enforces a single comparison strategy by dropping redundant checkboxes.
```json
{
  "label": "Compare Mode",
  "key": "compare_mode",
  "type": "multi",
  "flag": "--compare",
  "options": ["size", "modtime", "checksum"],
  "default": "size,modtime",
  "default_equipped": true,
  "rejects": ["checksum", "size_only"]
}
```
### Track Renames Strategy Expects Track Renames
Ensures a strategy cannot be selected without the underlying engine being active.
```json
{
  "label": "Track Renames Strategy",
  "key": "track_renames_strategy",
  "type": "combo",
  "flag": "--track-renames-strategy",
  "options": ["hash", "modtime", "leaf"],
  "expects": ["track_renames"]
}
```
### Max Lock Validation
Prevents deadlocks in background automation by enforcing the rclone technical minimum.
```json
{
  "label": "Max Lock",
  "key": "max_lock",
  "type": "entry",
  "flag": "--max-lock",
  "default": "2m",
  "validation": {"min": "2m"}
}
```
### Smart Preset: Safe Recovery
An example of a Procedure that uses a one-time lifecycle and a logic hook to rebuild state safely.
```json
{
  "label": "Safe Resync (Reset Button)",
  "key": "preset_safe_resync",
  "trigger_condition": "missing_listing_file",
  "lifecycle": "one_time",
  "python_hook": "normalize_session_path",
  "payload": {
    "expects": ["resync", "resync_mode", "dry_run"],
    "satisfy": {"resync_mode": "newer"}
  }
}
```