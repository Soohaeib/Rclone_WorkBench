# Rclone Workbench: A Linux Tray App for Rclone Bisync Management

This application provides a gamified, inventory-based framework for managing complex `rclone bisync` operations. It wraps rclone's powerful but intricate command-line interface into a safe, visual, and strictly validated GTK3 desktop experience, driven entirely by Type-Safe Python Dataclasses.

## System Architecture

The Workbench operates as a multi-layered ecosystem where data, logic, and execution are strictly decoupled.

* **`workbench_blueprint.py`**: *The Data Authority*. Defines the `SMART_SCHEMA` (Procedures) and strictly divides the tools into two core domain dictionaries: `BISYNC_SCHEMA` (flags unique to the bisync protocol, like `--resync`) and `GLOBAL_SCHEMA` (rclone engine flags, like `--dry-run` and `--filter`). These are dynamically aggregated into a unified `CONFIG_SCHEMA` at runtime to maintain downstream compatibility. This file is the absolute source of truth for all configuration schemas.

* **`rules_engine.py`**: *The Logic Processor*. A recursive engine that evaluates card relationships (`expects`, `rejects`, `satisfy`) to ensure a valid command-line state and enforces strict mathematical boundaries.

* **`smart_engine.py`**: *The Orchestrator & Scanner*. Analyzes the local cache for session listings to recommend Presets. Houses all custom **Python Hooks** for background environmental audits. It runs a strict 9-Point Safety Audit (checking for stale locks, empty directory traps, and caching filter MD5 hashes to `bisync_settings.json` to prevent mass deletions on filter changes).

* **`config_manager.py`**: *The Persistence Layer*. Handles saving/loading, dynamically prioritizes short/long flags, natively maps units, and compiles the final CLI arguments.

* **`rclone_runner.py`**: *The Backend Executor*. Manages subprocess calls, ensures graceful `SIGINT` shutdowns, and pipes raw JSONL output.

* **`log_formatter.py`**: *The Parser*. Translates raw rclone JSONL logs into human-readable actions. It intelligently parses log severities (DEBUG, ERROR, WARNING), truncates massive internal engine state dumps to prevent UI freezes, and dynamically color-codes the UI live feed.

* **`widget_factory.py`**: *The View/Factory*. Instantiates GTK widgets based on Dataclass properties and strictly enforces `clone_limit` duplication rules.

* **`workbench_ui.py`**: *The Canvas Linker*. The GTK3 interface controller where users interact with the Inventory, Smart Presets, and the active Canvas.

* **`app.py`**: *The Main Controller*. Manages the system tray, background threads, checks for Hook blockers, explicitly injects the `bisync` command, and safely triggers execution. It evaluates UI state to build dynamic, context-aware context menus (e.g., dynamically resolving and enabling shortcuts to local trash bins).

***

### The 9-Point Environmental Audit
Before any sync executes, `smart_engine.py` runs a lightning-fast local audit. It actively resolves your configured `--workdir` and `--cache-dir` system paths to locate internal states. If any of these fail, it injects an `_AUDIT_ERROR` key into the state, causing the Rules Engine to physically lock the UI's "Apply" button:
1. **First-Run Detection**: Mandates a resync if no `.lst` files exist.
2. **Filter Integrity**: Compares the current filter MD5 hash against the hash saved in `bisync_settings.json`.
3. **Critical Lockout**: Detects `.lst-err` files from prior crashes.
4. **Session Drift**: Normalizes anchor names to bypass false positives during `--dry-run`.
5. **Stale Lock PID Check**: Validates if `.lck` files belong to active or dead OS processes.
6. **Structural Flag Changes**: Detects changes to core comparison logic.
7. **Empty Path Trap**: Blocks `--resync` if the local path has 0 files, preventing catastrophic cloud wipes.
8. **Backend Capability**: Validates if the remote supports modtime comparisons.
9. **Access Health**: Verifies `RCLONE_TEST` sentinel files exist locally to prevent syncing against unmounted drives.

## The Blueprint Schema: Complete Manipulation Guide

To scale the application or add new flags, you only need to modify `workbench_blueprint.py` and write optional hooks in `smart_engine.py`. **Do not alter the UI or execution logic.**

### 1. Anatomy of a Smart Preset (`SMART_SCHEMA`)

Procedures are **Master Keys** that orchestrate application behavior, lock down safety parameters, and trigger Python validation scripts.

```python
@dataclass
class SmartPreset:
    label: str               # UI Name
    id: str                  # Unique ID for dependency resolution
    trigger_condition: str   # Logic trigger (e.g., "manual", "always_on")
    lifecycle: str           # "persistent" (stays on) or "one_time" (drops on exit 0)
    auto_apply: bool         # Apply payload without user confirmation
    python_hook: str         # The EXACT method name to call in smart_engine.py
    color: str               # UI Hex color (Presets retain free-form hexes for visual distinction)
    desc: str                # Tooltip explanation
    expects: List[str]       # ToolItem flags pulled onto the canvas
    satisfy: Dict[str, Any]  # Value enforcement map (Locks UI inputs)
    rejects: List[str]       # Conflicting ToolItem flags to automatically drop
```

#### Implementing Python Hooks for Presets

When you define `python_hook="audit_resync_environment"` in the Blueprint, you must create a matching function in `smart_engine.py`. Hooks intercept the state right before UI validation and execution. They must accept 4 arguments and return the modified state dict:

```python
# Inside smart_engine.py
def audit_resync_environment(profile, local_path, remote_path, live_state):
    # Perform logic...
    
    # Inject errors to trigger the Rules Engine UI block
    if critical_failure:
        live_state['_AUDIT_ERROR_CUSTOM'] = "Descriptive error message to show the user."
        
    # Or modify values dynamically (e.g., dynamic timestamps)
    live_state['conflict_suffix'] = f".{timestamp}.old"
    
    return live_state
```

### 2. Anatomy of an Inventory Item (`BISYNC_SCHEMA` & `GLOBAL_SCHEMA`)

To keep configurations semantically accurate, rclone flags are divided into `BISYNC_SCHEMA` (protocol-specific) and `GLOBAL_SCHEMA` (engine-wide). However, their internal structure is identical. Each flag is defined as a `ToolItem`.

```python
@dataclass
class ToolItem:
    label: str
    type: str                # Data/Widget type mapping
    flag: str                # Standard long flag (e.g., "--max-lock")
    severity: str            # Predefined UI Hex color set in `widget_factory.py` as THEME.
    short: str = ""          # Optional shorthand priority (e.g., "-v")
    default: Any = ""        # Starting value
    hidden: bool = False     # If True, removed from Inventory search (Smart Preset only)
    unit: str = ""           # Automatically appended to CLI string (e.g., "m" -> "2m")
    clone_limit: int = 0     # 0 = No duplication, -1 = Infinite splits, >0 = Max allowed splits
    options: List[str]       # Choices for 'combo' and 'multi' types
    validation: Dict[str, Union[int, float]] # Strict math boundaries e.g. {"min": 0, "max": 100}
    expects, rejects, satisfy: # Dependency arrays (same as Smart Presets)
```

#### The Semantic Severity Palette
Instead of hardcoding hex colors, the `ToolItem` schema uses a semantic `severity` attribute. The `widget_factory.py` automatically maps these to the application's global GTK theme (`THEME` dict). 

| Severity Level | Visual Color | Semantic Meaning & Use Case |
| :--- | :--- | :--- |
| **`critical`** | Red (`#c0392b`) | Destructive actions, abort thresholds, or safety overrides. |
| **`decision`** | Orange (`#e67e22`) | Logic that drastically alters which files are synced (e.g., filters). |
| **`safety`** | Green (`#27ae60`) | Non-destructive protections (e.g., trash bins, dry runs). |
| **`operational`** | Blue (`#2980b9`) | Standard engine behaviors and resilience logic. |
| **`heuristic`** | Purple (`#8e44ad`) | Advanced metadata, hashing, and tracking strategies. |
| **`system`** | Grey (`#7f8c8d`) | System paths, plumbing, and verbosity (The default fallback). |

#### Valid Types & Formatting

| Type         | UI Widget      | CLI Output Generation                | Use Case                                 |
| :----------- | :------------- | :----------------------------------- | :--------------------------------------- |
| **`check`**  | Toggle Switch  | `--flag` (No value attached)         | Simple booleans (e.g., `--dry-run`)      |
| **`entry`**  | Text Input     | `--flag "user_string"`               | Single strings, paths, suffixes          |
| **`text`**   | Multi-line Box | `--flag "line1" --flag "line2"`      | Complex inputs (e.g., `--filter`)        |
| **`combo`**  | Dropdown       | `--flag "selected_option"`           | Single-choice conflict resolution        |
| **`multi`**  | Checkboxes     | `--flag "opt1,opt2"`                 | Comma-separated list (e.g., `--compare`) |
| **`number`** | Spin Button    | `--flag "50unit"`                    | Values needing math validation and units |
| **`count`**  | Spin Button    | `-v -v -v` (Repeats short/long flag) | Verbose scaling, debug levels            |

#### Dependency Optimization (The DRY Principle)
You do not need to duplicate a flag in both `expects` and `satisfy`. 
* Use `expects=["--flag"]` when you want to pull a tool onto the canvas but leave it **unlocked** for the user to configure.
* Use `satisfy={"--flag": True}` when you want to pull a tool onto the canvas and **forcefully lock** its value, preventing the user from altering it. The engine will natively evaluate and apply any underlying `rejects` or `expects` that the forced tool possesses.
***

## Logic Engine & Split Mechanics

The Workbench evaluates dependencies (`expects`, `rejects`, `satisfy`) recursively. If a Smart Preset `satisfies` a ToolItem with a specific value, that ToolItem is forced onto the canvas, locked to that value, and the user is physically prevented from modifying or deleting it.


### The Duplication/Split Mechanic (`clone_limit`)

If a `text` or `entry` item has a `clone_limit` set (e.g., `clone_limit=-1`), a `+` button appears on the card.
* Clicking `+` generates an unblocked, uniquely hashed clone (e.g., `filter.a1b2c3`).
* This brilliantly allows a Smart Preset to permanently lock a safety rule on the base `filter` card, while allowing the user to spawn clones to add their own custom inclusion/exclusion rules alongside it.

***

## Usage & Operating Context

### System Tray & Application Lifecycle

* Run `python3 app.py` to initialize. The app parses `~/.config/rclone/rclone.conf` and creates an isolated background thread for each remote profile.
* **Context-Aware Tray:** You can manually trigger syncs, gracefully terminate processes (SIGINT), or monitor real-time parsed log outputs directly from the tray. The tray also calculates dynamic relative run-times (e.g., "5 mins ago") and features a dynamic **"Open Local Trash"** shortcut that calculates your active `--backup-dir1` path and grays itself out if the trash folder hasn't been created yet.

### Quality of Life: Native Drag-and-Drop (DND)
You do not need to manually type file paths. The Workbench fully supports native Linux Drag-and-Drop from Nautilus, Nemo, and Dolphin:
* Drag a folder into the **Local Path** bar, and it will clean and set the absolute path.
* Drag a file into a standard text `entry` (like `--filters-file`), and it will paste the absolute path.
* Drag multiple files into a multi-line `text` box (like `--filter`), and it will safely parse them and paste each path onto a new line.

### The Workbench UI

1. **Smart Presets (Left)**: Heuristic toggles. If the local audit detects a missing `.lst` file or an active `.lck` PID, the engine natively recommends or mandates these procedures.
2. **Inventory (Middle)**: A categorized sandbox of all Rclone flags.
3. **Canvas (Right)**: The live staging area. Any modifications update the **Live Preview** command. If an audit fails (e.g., empty source directory) or validation breaks, the UI turns red and safely disables execution.

### Sandbox Testing

You can safely test configurations without risking cloud data by setting up a local Rclone alias. Point your `rclone.conf` to a fake local cloud folder (`type = alias`), target it in the Workbench UI, and use the `--dry-run` flag to watch the Logic Engine manage Trash overlap protections and dependency cascades.
