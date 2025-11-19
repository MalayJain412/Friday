import logging
import logging.config
import os

class NoPymongoDebugFilter(logging.Filter):
    """Filter out very chatty pymongo debug messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("pymongo") and record.levelno <= logging.DEBUG:
            return False
        return True

def configure_logging():
    """Centralized logging configuration."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)4s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "filters": {
            "no_pymongo_debug": {
                "()": NoPymongoDebugFilter
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": log_level,
                "filters": ["no_pymongo_debug"],
                "stream": "ext://sys.stdout",
            }
        },
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
        "loggers": {
            "pymongo": {"level": "WARNING", "handlers": ["console"], "propagate": False},
            "urllib3": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        },
    }

    logging.config.dictConfig(config)