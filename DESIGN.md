# System Architecture & Design

The Workbench operates as a multi-layered ecosystem where data, logic, and execution are strictly decoupled. This allows developers to easily add new rclone flags without ever touching the UI code.

## Core Modules

* **`workbench_blueprint.py`** (*The Data Authority*): Defines the `SMART_SCHEMA` (Procedures) and divides the tools into `BISYNC_SCHEMA` and `GLOBAL_SCHEMA`. This file is the absolute source of truth for all configuration schemas.
* **`rules_engine.py`** (*The Logic Processor*): A recursive engine that evaluates card relationships (`expects`, `rejects`, `satisfy`) to ensure a valid command-line state and enforces strict mathematical boundaries.
* **`smart_engine.py`** (*The Orchestrator & Hardware Scanner*): Houses custom Python Hooks for background environmental audits. It polls host OS hardware limits (RAM/CPU) to calculate dynamic safety buffers.
* **`config_manager.py`** (*The Persistence Layer*): Handles saving/loading, dynamically compiles final CLI arguments, and runs **Garbage Collection** (`prune_orphaned_remotes`) to clean up the JSON state when profiles are deleted from `rclone.conf`.
* **`rclone_runner.py`** (*The Backend Executor*): Manages subprocess calls and non-blocking JSONL log piping. Supports strict Two-Stage Process Termination (SIGINT gracefully, escalating to SIGKILL).
* **`log_formatter.py`** (*The Parser*): Translates raw rclone JSONL logs into human-readable actions, intelligently parses log severities, and dynamically color-codes the live feed.
* **`widget_factory.py`** (*The View/Factory*): Instantiates GTK widgets based on Dataclass properties, natively handles DND events, and enforces duplication rules.
* **`ui_live_output.py`** (*The Log Viewer Component*): Handles GTK Notebook rendering, Pango text-tags, and live terminal output streaming.
* **`ui_inventory.py`** (*The Workbench Component*): Manages Smart Presets, the active configuration canvas, drag-and-drop mechanics, and compiling the CLI preview.
* **`workbench_ui.py`** (*The Global Controller*): The lightweight main window controller. It loads the base Glade file, manages the Global Command Center (Sync/Stop/Update), and securely links the UI sub-components together.
* **`app.py`** (*The System Tray Controller*): Manages background daemon threads and status emojis.

---

## The Automated Environmental & Hardware Audit
Before any sync executes, `smart_engine.py` runs a lightning-fast local audit. If any fail, it injects an `_AUDIT_ERROR` key into the state, physically locking the UI's "Apply" button:

1. **Hardware Resource Protection (Overdrive)**: Checks host CPU threads and available RAM.
2. **First-Run Detection**: Mandates a resync if no `.lst` files exist.
3. **Filter Integrity**: Compares current filter MD5 hash against the saved hash to prevent mass deletions on filter changes.
4. **Critical Lockout**: Detects `.lst-err` files from prior crashes.
5. **Stale Lock PID Check**: Validates if `.lck` files belong to active or dead OS processes.
6. **Structural Flag Changes**: Detects changes to core comparison logic.
7. **Empty Path Trap**: Blocks `--resync` if the local path has 0 files, preventing cloud wipes.
8. **Backend Capability**: Validates if the remote supports modtime comparisons.
9. **Star-Topology & Access Health**: Verifies sentinel files exist locally to prevent syncing against unmounted drives.

---

## The Blueprint Schema: Modification Guide

To scale the application or add new flags, **you only need to modify `workbench_blueprint.py`** and write optional hooks in `smart_engine.py`. Do not alter the UI logic.

### 1. Anatomy of a Smart Preset
Procedures are Master Keys that orchestrate application behavior, lock down safety parameters, and trigger Python validation scripts.

```python
@dataclass
class SmartPreset:
    label: str               # UI Name
    id: str                  # Unique ID for dependency resolution
    trigger_condition: str   # Logic trigger (e.g., "manual", "always_on")
    lifecycle: str           # "persistent" or "one_time" 
    auto_apply: bool         # Apply payload without user confirmation
    python_hook: str         # The EXACT method name to call in smart_engine.py
    color: str               # UI Hex color
    desc: str                # Tooltip explanation
    expects: List[str]       # ToolItem flags pulled onto the canvas
    satisfy: Dict[str, Any]  # Value enforcement map (Locks UI inputs)
    rejects: List[str]       # Conflicting ToolItem flags to automatically drop
```

### 2. Semantic Severity Palette
Instead of hardcoding hex colors, `ToolItem` schemas use a semantic `severity` attribute mapped to the application's global GTK theme:
* **`critical`** (Red): Destructive actions, abort thresholds.
* **`decision`** (Orange): Logic that drastically alters which files sync.
* **`safety`** (Green): Non-destructive protections (trash bins, dry runs).
* **`operational`** (Blue): Standard engine behaviors.
* **`heuristic`** (Purple): Advanced metadata, hashing.
* **`system`** (Grey): System paths, plumbing, and verbosity.

---

## The Smart Patcher (`smart_patcher.py`)
To prevent manual code-merging errors during updates, this app includes a built-in, context-aware JSON patcher. 
Instead of writing fragile regex or relying on line numbers, developers can ship updates via a `update.json` file. The patcher searches for exact anchor strings and safely performs idempotent injections (`replace`, `insert_before`, `insert_after`), completely automating codebase modifications.

## High-Performance GTK Rendering (Solving the "Ghost Lines" Bug)
GTK3 `TextView` widgets notoriously struggle when physical child widgets (like separators or boxes) are injected into rapidly appending text streams, causing "ghost line" rendering artifacts. 
To solve this, the Workbench UI strictly forbids inline widgets in the log tailer. Instead:
1. **Pure Text & Pango Tags:** All colored alerts, bolding, and URLs are handled natively via `Gtk.TextTag`, ensuring memory efficiency.
2. **Vertical Rhythm Stabilization:** We enforce `pixels-above-lines` and `pixels-below-lines` to lock the baseline height across every single line, preventing scroll-jumping.
3. **Truncation-Proof Tailing:** The `log_formatter.py` thread actively monitors file sizes. If a log file shrinks (deleted/truncated), it dynamically resets its read pointer, keeping the feed alive without crashing the daemon.