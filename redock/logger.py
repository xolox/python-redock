# Logging configuration for Redock.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 11, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import logging
import os

# External dependencies.
import coloredlogs
import verboselogs

def get_logger(name, level=logging.INFO):
    if 'REDOCK_DEBUG' in os.environ:
        level = logging.DEBUG
    logger = verboselogs.VerboseLogger(name)
    logger.setLevel(level)
    logger.addHandler(coloredlogs.ColoredStreamHandler(show_name=True))
    return logger

logger = get_logger('redock')

# vim: ts=4 sw=4 et
