# Logging configuration for Redock.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: August 6, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import logging
import os

# External dependencies.
import coloredlogs
import verboselogs

# Configure the root logger.
root_logger = logging.getLogger()
if 'REDOCK_DEBUG' in os.environ:
    root_logger.setLevel(logging.DEBUG)
else:
    root_logger.setLevel(logging.INFO)

# Silence the logger of an external dependency.
logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)

def get_logger(name):
    return verboselogs.VerboseLogger(name)

# vim: ts=4 sw=4 et
