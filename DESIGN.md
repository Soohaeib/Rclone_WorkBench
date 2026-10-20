# System Architecture & Design

The GTK application remains the primary implementation in `app.py`. The Qt
frontend is an additive alternative launched through `pyside_app.py`; neither
frontend replaces or imports the other.

The Workbench operates as a multi-layered ecosystem where data, logic, and execution are strictly decoupled. This allows developers to easily add new rclone flags without ever touching the UI code.

## Core Modules

* **`shared/`** (*Frontend-neutral logic*): Contains the schema, configuration, rules, audits, log parser, process adapter, and `RcloneEngine`. It imports neither GTK nor Qt.
* **`gtk_app/`** (*GTK Front End*): Contains the original GTK controller, Glade panels, widget factory, and `workbench.glade` asset.
* **`qt_app/`** (*Qt Front End*): Contains the PySide6 window components, tray controller, and QSS stylesheet.
* **`app.py`** (*GTK Entry Point*): Loads only `gtk_app` and `shared`.
* **`pyside_app.py`** (*Qt Entry Point*): Loads only `qt_app` and `shared`.

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