"""Backward-compatible process adapter for the shared engine."""

from .engine import RcloneEngine


def kill_process(process, force=False):
    """Stop a legacy subprocess through the shared execution engine."""
    if process is None or process.poll() is not None:
        return
    engine = RcloneEngine("", "")
    engine.proc = process
    engine.stop_process(force=force)
