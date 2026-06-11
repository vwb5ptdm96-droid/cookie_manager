"""Example site script. Replace this body with the real login flow."""

from common.logger import setup_logger

logger = setup_logger("refresher.weibo")


def refresh(task: dict) -> bool:
    logger.error("[%s] refresh script is not implemented", task["name"])
    return False

