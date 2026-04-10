# Rclone Workbench: A Linux Tray App for Rclone Bisync Management

This application provides a gamified, inventory-based framework for managing complex `rclone bisync` operations. It wraps rclone's powerful but intricate command-line interface into a safe, visual, and strictly validated GTK3 desktop experience, driven entirely by Type-Safe Python Dataclasses.

## 🏗️ System Architecture

The Workbench operates as a multi-layered ecosystem where data, logic, and execution are strictly decoupled.

* **`workbench_blueprint.py`**: *The Data Authority*. Defines the `CONFIG_SCHEMA` (Tools) and `SMART_SCHEMA` (Procedures) using strict Python Dataclasses. This is the absolute source of truth for all configuration schemas.

* **`rules_engine.py`**: *The Logic Processor*. A recursive engine that evaluates card relationships (`expects`, `rejects`, `satisfy`) to ensure a valid command-line state. It gracefully handles `.HEXCODE` cloned widgets.

* **`smart_engine.py`**: *The Orchestrator & Scanner*. A unified module that analyzes the local `~/.cache/rclone/bisync` directory for session listings to recommend Presets, and executes side-effect methods (e.g., injecting local absolute paths) at execution and preview time.

* **`config_manager.py`**: *The Persistence Layer*. Handles the loading and saving of `bisync_settings.json`, ensures profile integrity, and compiles the final CLI arguments.

* **`rclone_runner.py`**: *The Backend Executor*. Manages the subprocess calls to rclone bisync, appends session dividers to logs, and pipes raw JSONL output.

* **`log_formatter.py`**: *The Parser*. Translates raw rclone JSONL logs into human-readable actions for the UI live feed.

* **`widget_factory.py`**: *The View/Factory*. Responsible solely for instantiating and configuring GTK widgets (Canvas cards and Inventory chips) based on Dataclass properties.

* **`workbench_ui.py`**: *The Canvas Linker*. The GTK3 interface controller where users interact with the Inventory, Smart Presets, and the active command Canvas.

* **`app.py`**: *The Main Controller*. Manages the application lifecycle, system tray integration, background execution threads, and cross-module communication.

> **Note on Environment**: The Workbench explicitly targets the Linux environment, resolving `RCLONE_CONF_PATH` at `~/.config/rclone/rclone.conf` and managing session state within `~/.cache/rclone/bisync`.

## ⚙️ The Blueprint Schema

### 1. Anatomy of a Smart Preset

Procedures in `SMART_SCHEMA` are **Master Keys** that orchestrate the application's behavior. They are defined as `SmartPreset` dataclasses.

```
@dataclass
class SmartPreset:
    label: str               # UI Name
    key: str                 # Unique ID for dependency resolution
    trigger_condition: str   # Logic trigger (e.g., "missing_listing_file")
    auto_apply: bool         # Apply payload without user confirmation
    lifecycle: str           # "one_time" or "persistent"
    python_hook: str         # Method name in smart_engine.py for live injection
    color: str               # UI Hex color
    desc: str                # Technical strategy explanation
    expects: List[str]       # Required ToolItem keys
    satisfy: Dict[str, Any]  # Value enforcement map
    rejects: List[str]       # Conflicting ToolItem keys

```

**Key Behaviors:**

* **`lifecycle="one_time"`**: Preset is "dropped" by the logic engine after a successful `exit 0` from rclone (prevents endless resync loops).

* **`satisfy`**: Maps `{key: value}` used to **Lock** flags to safe values (e.g., forcing a specific `--filter` layout).

### 2. Anatomy of an Inventory Item

Each flag or option in `CONFIG_SCHEMA` is a `ToolItem` dataclass.

```
@dataclass
class ToolItem:
    label: str
    key: str
    type: str                # UI Widget type ('check', 'entry', 'multi', etc.)
    flag: str                # Rclone flag (e.g., "--resync")
    short: str = ""          # Optional shorthand (e.g., "-v")
    default: Any = ""
    default_equipped: bool = False
    color: str = "#FFFFFF"
    desc: str = ""
    options: List[str] = field(default_factory=list)
    rejects: List[str] = field(default_factory=list)
    expects: List[str] = field(default_factory=list)
    satisfy: Dict[str, Any] = field(default_factory=dict)
    validation: Dict[str, str] = field(default_factory=dict)

```

**Supported Widget Types:**

1. **`check`**: A toggle-style card. Emits the flag with no value (e.g., `--resync`).
2. **`entry`**: A single text input. Emits `--flag "value"`.
3. **`combo`**: A dropdown selector for a predefined value from the `options` array.
4. **`multi`**: Generates a FlowBox of independent checkboxes. Emits a comma-separated string (e.g., `--compare "size,modtime"`).
5. **`count`**: A repeatable counter (e.g., `-v`, `-vv`). UI renders a SpinButton; generator emits repeated shorthand flags (e.g., `-vvv`).
6. **`text`**: A multiline text field.

   * **The Split Mechanic (➕)**: Base `text` items feature a split button in the UI. Clicking it spawns an independent clone (e.g., `filter.a1b2c3`) to allow unlimited repeating flags, crucial for multiple `--filter` lines.

## 🧠 Logic Engine & Rules

The Workbench uses a triple-constraint system evaluated recursively by `rules_engine.py`:

1. **`expects`**: Prerequisites. If a Tool is equipped, these keys are pulled onto the Canvas automatically.
2. **`rejects`**: Mutual exclusion. Equipping a card with a "Conflict" drops the offending card from the Canvas.
3. **`satisfy`**: Value enforcer. Forces specific values on other cards and **locks** the input widget in the UI to prevent user error.

### The Duality of Locked Arrays

When a Smart Preset uses `satisfy` to lock a text item (e.g., locking `--filter` to natively exclude trash bins with Rclone's dynamic `{2006-01-02_150405}` variables), the base widget's text field and `✕` close button are disabled.

However, the `➕` split button remains active. This brilliantly allows the system to:

* **Guarantee** that safety filters remain untouched.

* **Permit** the user to spawn unblocked `.HEXCODE` clones to add custom filter rules alongside the locked ones.

## 🖥️ Usage Guidelines & Working Structure

### The System Tray

When launched via `app.py`, the Workbench minimizes to a system tray icon (`network-server`).

* The tray parses `~/.config/rclone/rclone.conf` and creates an independent background thread for each remote profile.

* **Status Indicators**: Each profile displays a colored dot reflecting its state (🟢 Ready, 🔵 Syncing, 🔴 Error, ⚪ Never Synced).

* You can manually trigger a sync, kill a hanging process, or open the Live Output/Inventory directly from the tray menu.

### The Workbench UI

The main configuration window is divided into three distinct panels:

1. **Smart Presets (Left)**: Heuristic-driven toggles. The `smart_engine` scans your environment on load. If it detects a missing listing file, it will recommend the "Master Safe Resync" preset to recover safely.
2. **Inventory Tools (Middle)**: A categorized sandbox of all available Rclone flags defined in the Blueprint. Click a chip to equip it to the Canvas.
3. **Active Canvas (Right)**: The live staging area. Cards here represent the exact state that will be fed to Rclone.

   * Editing values, splitting arrays, or toggling presets immediately updates the **Live Command Preview** at the bottom of the screen.

   * If a rule validation fails (e.g., `--max-lock` is less than `2m`), the preview console turns red and the "Apply" button is disabled.

### Live Outputs

During execution, rclone is run with `--use-json-log`. The `rclone_runner.py` pipes this output to a `.jsonl` file in the logs directory.

* The **Live Outputs** tab reads this file in real-time using a daemon tailer.

* The `log_formatter.py` strips out terminal colors and translates raw JSON logs into a clean, human-readable terminal feed, extracting transfer speeds, ETA, and specific file actions directly to the UI.

* Session dividers automatically separate runs in the log file, keeping history legible.

### Adding New Flags

To add new Rclone features, **do not touch the python logic code**. Simply open `workbench_blueprint.py` and add a new `ToolItem` to the `CONFIG_SCHEMA`. The Factory, Rules Engine, and Config Manager will automatically render, validate, and execute it.
