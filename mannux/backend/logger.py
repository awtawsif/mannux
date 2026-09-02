import logging
import sys

def setup_logger(verbose: bool = False, debug: bool = False) -> logging.Logger:
    logger = logging.getLogger("mannux")
    if logger.handlers:
        return logger

    level = logging.INFO
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="[%(levelname)s] (%(name)s) %(message)s",
        datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

log = logging.getLogger("mannux")
