"""
日志配置 — 统一日志格式，同时输出到文件和控制台。
"""
import os
import sys
import logging
from datetime import datetime


def setup_logger(name: str = "cookie_manager") -> logging.Logger:
    log_dir = os.getenv("LOG_DIR", "./logs")
    log_level = os.getenv("LOG_LEVEL", "INFO")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(console)

    # 文件 handler — 按天轮转
    log_file = os.path.join(log_dir, f"{datetime.now():%Y-%m-%d}.log")
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(log_level)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(fh)

    return logger
