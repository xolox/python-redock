# Logging configuration for the redock program.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 7, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import logging

# External dependencies.
import coloredlogs
import verboselogs

# Initialize the logger.
logger = verboselogs.VerboseLogger('redock')
logger.setLevel(logging.INFO)
logger.addHandler(coloredlogs.ColoredStreamHandler())

# vim: ts=4 sw=4 et
