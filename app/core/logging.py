import logging
import sys
from app.core.config import settings


def setup_logging() -> None:
    log_level = logging.DEBUG if settings.ENVIRONMENT == "development" else logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


logger = logging.getLogger("daweros_api")