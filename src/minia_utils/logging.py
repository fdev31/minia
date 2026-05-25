"""Central logging configuration for the minia project.

All minia components should use ``logging.getLogger(__name__)`` to obtain a
logger.  The root logger is configured once by ``configure_logging()``
(called from each entry point's ``main()``) and all child loggers inherit its
handlers through propagation.

Log level resolution (highest → lowest priority):

1. ``MINIA_LOG_LEVEL`` environment variable — allows a parent process
   (e.g. ``minia`` / mother_forker) to propagate its log level to
   subprocesses.
2. ``--log-level`` CLI argument (if the entry point supports it).
3. ``config.default.log_level`` from the TOML config file.
4. Hardcoded default ``"INFO"``.

Usage
-----
In an entry-point module::

    from minia_utils.logging import configure_logging
    configure_logging(log_level="DEBUG", log_file="debug.log", add_console=True)

In any other module::

    import logging
    logger = logging.getLogger(__name__)

"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_LOG_FILE: str = "debug.log"
DEFAULT_LOG_LEVEL: str = "INFO"
MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT: int = 5  # Keep 5 rotated backups

_FORMAT_STRING: str = "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_initialized: bool = False


def _build_formatter() -> logging.Formatter:
    """Return a new formatter instance."""
    return logging.Formatter(_FORMAT_STRING, datefmt=_DATE_FORMAT)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def configure_logging(
    log_level: str | None = None,
    log_file: str | None = None,
    add_console: bool = True,
) -> None:
    """Configure the root logger for the entire minia application.

    This function is idempotent — calling it multiple times has no effect
    after the first successful call.

    Parameters
    ----------
    log_level :
        Logging level as a string (``"DEBUG"``, ``"INFO"``, ``"WARNING"``,
        ``"ERROR"``, ``"CRITICAL"``).  The effective level is determined by:

        1. ``MINIA_LOG_LEVEL`` environment variable (highest priority —
           allows parent processes to propagate their level to children).
        2. The *log_level* argument passed to this function.
        3. ``config.default.log_level`` from the TOML config (caller's
           responsibility to resolve before calling).
        4. Hardcoded default ``"INFO"``.

    log_file :
        Path to the log file.  If *None*, defaults to ``debug.log``.
    add_console :
        Whether to attach a ``StreamHandler`` (stdout) in addition to the
        rotating file handler.

    Notes
    -----
    * The root logger is set to ``DEBUG`` so that every handler's own level
      filter is the only gate — this lets the file handler capture DEBUG
      messages while the console handler can be set to a higher level.
    * All child loggers (``logging.getLogger(__name__)``) propagate to the
      root logger by default, so they automatically receive the configured
      handlers.
    """
    global _initialized

    if _initialized:
        return

    # Resolve effective log level: env var > explicit arg > default
    env_level = os.environ.get("MINIA_LOG_LEVEL")
    if env_level:
        effective_level = env_level.upper()
    elif log_level is not None:
        effective_level = log_level.upper()
    else:
        effective_level = DEFAULT_LOG_LEVEL

    if log_file is None:
        log_file = DEFAULT_LOG_FILE

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Let handlers filter

    fmt = _build_formatter()

    # --- File handler (rotating) ----------------------------------------
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        mode="a",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
    )
    file_handler.setLevel(getattr(logging, effective_level, logging.INFO))
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # --- Console handler -------------------------------------------------
    if add_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, effective_level, logging.INFO))
        console_handler.setFormatter(fmt)
        root.addHandler(console_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger with the given name.

    The logger inherits handlers from the root logger once
    ``configure_logging()`` has been called.

    This is a thin wrapper around ``logging.getLogger()`` provided for
    explicitness and future extensibility.
    """
    return logging.getLogger(name)


def resolve_log_level(config: Any, section: str, default: str = "INFO") -> str:
    """Resolve log level from config section with fallback chain.

    Priority: section.log_level > default.log_level > *default*.

    Parameters
    ----------
    config :
        The minia config object (has ``default`` and the named *section*).
    section :
        Config section name (e.g. ``"tts"``, ``"client"``, ``"audio"``).
    default :
        Fallback value when neither section nor default section has a log level.

    Returns
    -------
    str
        Upper-cased log level string.
    """
    section_obj = getattr(config, section, None)
    if section_obj is not None:
        level = getattr(section_obj, "log_level", None)
        if level is not None:
            return level.upper()
    if hasattr(config, "default"):
        level = getattr(config.default, "log_level", None)
        if level is not None:
            return level.upper()
    return default.upper()
