"""Logging setup for the apply pipeline.

One root logger (`apply`) with child loggers per stage. Default level INFO;
`--quiet` raises to WARNING, `--verbose` drops to DEBUG. Output goes to stderr
with no level/timestamp prefix so user-facing progress reads like plain text.
"""

from __future__ import annotations

import logging

_ROOT = "apply"
_configured = False


def configure(quiet: bool = False, verbose: bool = False) -> None:
    """Set up the root `apply` logger. Idempotent."""
    global _configured
    level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger(_ROOT)
    logger.setLevel(level)
    if not _configured:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the `apply` namespace."""
    short = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{_ROOT}.{short}")
