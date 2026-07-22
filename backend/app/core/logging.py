import logging
import sys
from loguru import logger
from app.core.config import settings


class InterceptHandler(logging.Handler):
    """
    Default handler to intercept standard logging records and redirect them to Loguru.
    """
    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists.
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message.
        frame = sys._getframe(6)
        depth = 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    # Clear existing handlers from root logger
    logging.root.handlers = []
    
    # Define libraries whose logs we want to intercept
    loggers = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy.engine",
        "celery",
    )
    
    intercept_handler = InterceptHandler()
    
    # Intercept loggers
    for logger_name in loggers:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [intercept_handler]
        logging_logger.propagate = False

    # Standard configuration for the root logger
    logging.root.setLevel(settings.LOG_LEVEL.upper())
    logging.root.addHandler(intercept_handler)

    # Set up Loguru output format
    log_level = settings.LOG_LEVEL.upper()
    
    logger.configure(
        handlers=[
            {
                "sink": sys.stdout,
                "level": log_level,
                "format": (
                    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                    "<level>{level: <8}</level> | "
                    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                    "<level>{message}</level>"
                ),
            }
        ]
    )
