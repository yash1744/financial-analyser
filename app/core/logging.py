import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with a single stdout handler.

    Containers expect logs on stdout; anything fancier (JSON, shipping)
    belongs in the log collector, not the app.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Avoid duplicate handlers when uvicorn reloads the app
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)

    # Align uvicorn's loggers with ours instead of letting them double-log
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
