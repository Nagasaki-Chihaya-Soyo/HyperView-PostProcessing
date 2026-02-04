import logging
import os
from datetime import datetime


def setup_logger(log_dir: str, name: str = "hv_tool"):
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    log_file = os.path.join(log_dir, f"{name}_{datetime.now():%Y%m%d_%H%M%S}.log")
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter(fmt='[%(asctime)s] %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

_logger = None

def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = setup_logger("workdir/logs")
    return _logger

def log_info(msg: str):
    get_logger().info(msg)

def log_error(msg: str):
    get_logger().error(msg)

def log_debug(msg: str):
    get_logger().debug(msg)
