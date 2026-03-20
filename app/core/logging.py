import sys
from loguru import logger


def setup_logging(debug: bool = False) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level="DEBUG" if debug else "INFO",
        backtrace=debug,
        diagnose=debug,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
