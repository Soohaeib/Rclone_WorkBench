"""GTK-free execution engine for rclone bisync sessions."""

import datetime
import hashlib
import json
import os
import signal
import subprocess
import threading
from typing import Callable, Optional

from . import config_manager, rules_engine, smart_engine, workbench_blueprint


StateCallback = Callable[["RcloneEngine", str], None]
LogCallback = Callable[["RcloneEngine", str], None]


class RcloneEngine:
    """Coordinates audits, bisync execution, logging, and process supervision.

    ``state_callback`` receives the engine and a state name whenever the state
    changes. ``log_callback`` receives each raw rclone output line.
    """

    def __init__(
        self,
        profile: str,
        local_path: str,
        state_callback: Optional[StateCallback] = None,
        log_callback: Optional[LogCallback] = None,
    ):
        self.profile = profile
        self.local_path = local_path
        self.state_callback = state_callback
        self.log_callback = log_callback
        self.trigger = threading.Event()
        self._shutdown = threading.Event()
        self._worker = threading.Thread(target=self._run_loop, daemon=True)

        self.run_state = False
        self.proc = None
        self.kill_clicks = 0
        from . import log_formatter
        self.last = log_formatter.get_last_run_time(profile)
        status = self._last_status()
        self.err = status == "Failed"
        self.cancelled = status == "Cancelled"
        self.last_error = None

    def start(self):
        self._worker.start()
        return self

    def trigger_sync(self):
        self.trigger.set()

    def stop(self, force=False):
        self._shutdown.set()
        self.trigger.set()
        self.stop_process(force=force)

    def stop_process(self, force=False):
        process = self.proc
        if process is None or process.poll() is not None:
            return
        target_signal = signal.SIGKILL if force else signal.SIGINT
        try:
            os.killpg(os.getpgid(process.pid), target_signal)
        except ProcessLookupError:
            pass

    def hardware_bounds(self):
        return smart_engine.get_hardware_bounds()

    def _emit_state(self, state):
        if self.state_callback:
            self.state_callback(self, state)

    def _last_status(self):
        from . import log_formatter
        return log_formatter.get_last_run_status(self.profile)

    def _run_loop(self):
        while not self._shutdown.is_set():
            self.trigger.wait()
            self.trigger.clear()
            if not self._shutdown.is_set():
                self._run_sync()

    def _run_sync(self):
        self.run_state, self.err, self.cancelled = True, False, False
        self.kill_clicks = 0
        self._emit_state("starting")

        cfg = config_manager.load_config()
        live_state = cfg.get("remote_configs", {}).get(self.profile, {}).copy()
        remote_path = live_state.get("remote_path", "")
        live_state = smart_engine.audit_resync_environment(
            self.profile, self.local_path, remote_path, live_state
        )
        audit_errors = [value for key, value in live_state.items() if key.startswith("_AUDIT_ERROR")]
        if audit_errors:
            self.err, self.run_state, self.last = True, False, "Blocked"
            self.last_error = audit_errors[0]
            self._emit_state("blocked")
            self._emit_log(self.last_error)
            return

        if "--backup-dir1" in live_state:
            live_state = smart_engine.setup_trash_bins(
                self.profile, self.local_path, remote_path, live_state
            )

        flags = config_manager.build_base_args(self.profile, cfg, live_state)
        remote_full = f"{self.profile}:{remote_path}" if remote_path else f"{self.profile}:"
        args = ["bisync", self.local_path, remote_full] + flags
        result = self._execute(args)

        self.run_state = False
        self.proc = None
        if self.kill_clicks:
            self.cancelled, self.err = True, False
        else:
            self.err = not result["success"]
            self.last = datetime.datetime.now().isoformat()
        self._emit_state("cancelled" if self.cancelled else "failed" if self.err else "completed")

        if not self.err:
            self._persist_successful_run(cfg, live_state)

    def _execute(self, args):
        os.makedirs(workbench_blueprint.LOG_DIR, exist_ok=True)
        log_path = os.path.join(
            workbench_blueprint.LOG_DIR, f"{self.profile}_sync.jsonl"
        )
        command = ["rclone"] + args + ["-v", "--use-json-log", "--stats", "1s", "--stats-one-line"]
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps({
                "session_start": datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            }) + "\n")

        self.proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=os.setsid,
        )
        self._emit_state("running")
        with open(log_path, "a", encoding="utf-8") as log_file:
            for line in iter(self.proc.stdout.readline, "") if self.proc.stdout else ():
                log_file.write(line)
                log_file.flush()
                self._emit_log(line)
            self.proc.wait()
        return {"success": self.proc.returncode == 0, "process": self.proc}

    def _emit_log(self, line):
        if self.log_callback:
            self.log_callback(self, line)

    def _persist_successful_run(self, cfg, live_state):
        profile_cfg = cfg.setdefault("remote_configs", {}).setdefault(self.profile, {})
        filter_text = "\n".join(
            value for key, value in live_state.items()
            if key.startswith("--filter") and isinstance(value, str)
        )
        filter_hashes = cfg.setdefault("filter_hashes", {})
        if filter_text:
            filter_hashes[self.profile] = hashlib.md5(filter_text.encode()).hexdigest()
        else:
            filter_hashes.pop(self.profile, None)

        dropped = False
        for item in workbench_blueprint.SMART_SCHEMA.get("Smart Automations", []):
            if getattr(item, "lifecycle", "persistent") == "one_time" and profile_cfg.get(item.id):
                profile_cfg.pop(item.id, None)
                for key in getattr(item, "satisfy", {}):
                    profile_cfg.pop(key, None)
                for key in getattr(item, "expects", []):
                    profile_cfg.pop(key, None)
                dropped = True
        if dropped:
            active_keys = [
                key for key, value in profile_cfg.items()
                if value is True or (isinstance(value, str) and value)
                or type(value) in (int, float)
            ]
            _, merged, _, _ = rules_engine.evaluate_state(
                active_keys, profile_cfg, rules_engine.get_item_lookup()
            )
            cfg["remote_configs"][self.profile] = merged
        config_manager.save_config(cfg)
