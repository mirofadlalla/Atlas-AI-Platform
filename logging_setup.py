import logging
from pythonjsonlogger import jsonlogger

import sys


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    logHandler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(message)s")
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
