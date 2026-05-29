from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(
    *,
    logger_name: str = "xm_gold_ai_trader",
    log_path: str | Path = "logs/xm_gold_ai_trader.log",
    level: int = logging.INFO,
) -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[file_handler, console_handler], force=True)
    return logging.getLogger(logger_name)

