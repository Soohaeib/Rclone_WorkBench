"""Backward-compatible imports for the GTK-free rclone engine."""

from engine import RcloneEngine


def kill_process(process, force=False):
    """Compatibility helper for integrations that still hold a Popen object."""
    if process is None or process.poll() is not None:
        return
    engine = RcloneEngine("", "")
    engine.proc = process
    engine.stop_process(force=force)
