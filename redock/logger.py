# Logging configuration for Redock.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 14, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import logging
import os

# External dependencies.
import coloredlogs
import verboselogs

# Install an output handler on the root logger.
root_logger = logging.getLogger()
root_logger.addHandler(coloredlogs.ColoredStreamHandler(show_name=True))
if 'REDOCK_DEBUG' in os.environ:
    root_logger.setLevel(logging.DEBUG)
else:
    root_logger.setLevel(logging.INFO)

# Silence the logger of an external dependency.
logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)

def get_logger(name):
    return verboselogs.VerboseLogger(name)

logger = get_logger('redock')

# vim: ts=4 sw=4 et
