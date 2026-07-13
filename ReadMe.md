# Rclone Workbench: A Linux Tray App for Rclone Bisync Management

This application provides a gamified, inventory-based framework for managing complex `rclone bisync` operations. It wraps rclone's powerful but intricate command-line interface into a safe, visual, strictly validated GTK3 desktop experience driven entirely by Type-Safe Python Dataclasses.

## System Architecture

The Workbench operates as a multi-layered ecosystem where data, logic, and execution are strictly decoupled.

* **`workbench_blueprint.py`**: *The Data Authority*. Defines the `SMART_SCHEMA` (Procedures) and divides the tools into two core domain dictionaries: `BISYNC_SCHEMA` (protocol-specific) and `GLOBAL_SCHEMA` (engine-wide). These are dynamically aggregated at runtime. This file is the absolute source of truth for all configuration schemas.
* **`rules_engine.py`**: *The Logic Processor*. A recursive engine that evaluates card relationships (`expects`, `rejects`, `satisfy`) to ensure a valid command-line state and enforces strict mathematical boundaries.
* **`smart_engine.py`**: *The Orchestrator & Hardware Scanner*. Houses all custom Python Hooks for background environmental audits. It actively polls host OS hardware limits (RAM/CPU) to calculate dynamic safety buffers and evaluates local cache states to enforce required presets.
* **`config_manager.py`**: *The Persistence Layer*. Handles saving/loading, dynamically compiles the final CLI arguments, and runs dynamic **Garbage Collection** (`prune_orphaned_remotes`) to clean up the JSON state when profiles are deleted from `rclone.conf`.
* **`rclone_runner.py`**: *The Backend Executor*. Manages subprocess calls and non-blocking JSONL log piping. It supports a strict **Two-Stage Process Termination**: Graceful `SIGINT` first, escalating to a Forceful `SIGKILL` on subsequent requests.
* **`log_formatter.py`**: *The Parser*. Translates raw rclone JSONL logs into human-readable actions. It intelligently parses log severities, dynamically color-codes the live feed, and physically strips massive internal Go pointer structs from `-vv` debug logs to prevent GTK UI freezing.
* **`widget_factory.py`**: *The View/Factory*. Instantiates GTK widgets based on Dataclass properties, natively handles Drag-and-Drop (DND) events, and enforces `clone_limit` duplication rules.
* **`workbench_ui.py`**: *The Canvas Linker*. The GTK3 interface controller featuring a real-time **Global Command Center**. It runs a background polling loop to update the UI with active system loads, enforces dynamic hardware boundaries on UI SpinButtons, and manages the Active Canvas.
* **`app.py`**: *The System Tray Controller*. Manages background daemon threads, dynamic relative run-times (e.g., "5 mins ago"), and resolves context-aware shortcuts (like identifying active local trash bin paths).

***

### The Automated Environmental & Hardware Audit
Before any sync executes, `smart_engine.py` runs a lightning-fast local audit. If any of these fail, it injects an `_AUDIT_ERROR` key into the state, causing the Rules Engine to physically lock the UI's "Apply" button:

1. **Hardware Resource Protection (Overdrive)**: Calculates host CPU threads and available RAM. If `--fast-list` is requested but system RAM is too low, it disables the flag to prevent an Out-Of-Memory (OOM) freeze. It also actively clamps parallel `--checkers` and `--transfers` to a 95% maximum hardware threshold.
2. **First-Run Detection**: Mandates a resync if no `.lst` files exist.
3. **Filter Integrity**: Compares the current filter MD5 hash against the hash saved in `bisync_settings.json` to prevent mass deletions on filter changes.
4. **Critical Lockout**: Detects `.lst-err` files from prior crashes.
5. **Stale Lock PID Check**: Validates if `.lck` files belong to active or dead OS processes.
6. **Structural Flag Changes**: Detects changes to core comparison logic (e.g. requiring a resync when `track-renames` logic changes).
7. **Empty Path Trap**: Blocks `--resync` if the local path has 0 files, preventing catastrophic cloud wipes.
8. **Backend Capability**: Validates if the remote supports modtime comparisons (blocking unsupported protocols like `ftp` or `photos`).
9. **Star-Topology & Access Health**: Verifies `RCLONE_TEST` sentinel files exist locally to prevent syncing against unmounted drives.

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
    color: str               # UI Hex color
    desc: str                # Tooltip explanation
    expects: List[str]       # ToolItem flags pulled onto the canvas
    satisfy: Dict[str, Any]  # Value enforcement map (Locks UI inputs)
    rejects: List[str]       # Conflicting ToolItem flags to automatically drop
```

### 2. Anatomy of an Inventory Item (`BISYNC_SCHEMA` & `GLOBAL_SCHEMA`)

```python
@dataclass
class ToolItem:
    label: str
    type: str                # 'check', 'entry', 'text', 'combo', 'multi', 'number', 'count'
    flag: str                # Standard long flag (e.g., "--max-lock")
    severity: str            # Maps to global semantic themes (e.g., "critical", "safety")
    short: str = ""          # Optional shorthand priority (e.g., "-v")
    default: Any = ""        # Starting value
    hidden: bool = False     # If True, removed from Inventory search
    unit: str = ""           # Automatically appended to CLI string (e.g., "m" -> "2m")
    clone_limit: int = 0     # 0 = No duplication, -1 = Infinite splits
    options: List[str]       # Choices for 'combo' and 'multi' types
    validation: Dict[str, Union[int, float]] # Strict math boundaries e.g. {"min": 0, "max": 100}
    expects, rejects, satisfy: # Dependency arrays
```

#### The Semantic Severity Palette
Instead of hardcoding hex colors, the `ToolItem` schema uses a semantic `severity` attribute mapped automatically to the application's global GTK theme:
* **`critical`** (Red): Destructive actions, abort thresholds, or overrides.
* **`decision`** (Orange): Logic that drastically alters which files sync (filters, conflicts).
* **`safety`** (Green): Non-destructive protections (trash bins, dry runs).
* **`operational`** (Blue): Standard engine behaviors and resilience logic.
* **`heuristic`** (Purple): Advanced metadata, hashing, and tracking strategies.
* **`system`** (Grey): System paths, plumbing, and verbosity (Default).

#### Dependency Optimization (The DRY Principle)
* Use `expects=["--flag"]` to pull a tool onto the canvas but leave it **unlocked** for the user to configure.
* Use `satisfy={"--flag": True}` to pull a tool onto the canvas and **forcefully lock** its value, physically preventing the user from altering it.

### The Duplication/Split Mechanic (`clone_limit`)
If a `text` or `entry` item has a `clone_limit` set (e.g., `clone_limit=-1`), a `+` button appears on the card. Clicking `+` generates an unblocked, uniquely hashed clone (e.g., `filter.a1b2c3`). This allows a Smart Preset to permanently lock a safety rule on the base `filter` card, while allowing the user to spawn clones to add custom inclusion/exclusion rules alongside it.

***

## Usage & Operating Context

### Quality of Life: Native Drag-and-Drop (DND)
You do not need to manually type file paths. The Workbench fully supports native Linux Drag-and-Drop from Nautilus, Nemo, and Dolphin:
* **Local Path**: Drag a folder into the top bar to set the absolute path.
* **Entries**: Drag a file into a standard `entry` to paste the absolute path.
* **Multi-line Text**: Drag multiple files into a multi-line `text` box (like `--filter`) to safely parse and paste each path onto a new line.

### System Tray & Global Command Center
* Run `python3 app.py` to initialize. The app operates largely in the background.
* **Global Command Center**: When the UI is open, a top action bar provides instantaneous control over the selected profile. It features unified **Sync** and **Stop** buttons (which intelligently escalate from a graceful stop to a forceful process destruction), dynamic shortcuts to localized trash bins, and a real-time **System Info Popover** displaying active logical cores, 1-minute system load, and available RAM.

### Sandbox Testing
You can safely test configurations without risking cloud data by setting up a local Rclone alias. Point your `rclone.conf` to a fake local directory (`type = alias`), target it in the Workbench UI, and use the `--dry-run` flag to watch the Logic Engine manage Trash overlap protections, Overdrive hardware clamping, and dependency cascades.