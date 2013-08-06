# Command line interface for Redock, a human friendly wrapper around Docker.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: August 6, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import getopt
import logging
import os
import subprocess
import sys
import textwrap

# External dependencies.
import coloredlogs
from humanfriendly import Timer

# Modules included in our package.
from redock.api import Container, Image
from redock.logger import get_logger, root_logger

logger = get_logger(__name__)

def main():
    """
    Command line interface for the ``redock`` program.
    """
    # Initialize coloredlogs.
    coloredlogs.install()
    # Parse and validate the command line arguments.
    try:
        # Command line option defaults.
        hostname = None
        message = None
        # Parse the command line options.
        options, arguments = getopt.getopt(sys.argv[1:], 'b:n:m:vh',
                                          ['hostname=', 'message=', 'verbose', 'help'])
        for option, value in options:
            if option in ('-n', '--hostname'):
                hostname = value
            elif option in ('-m', '--message'):
                message = value
            elif option in ('-v', '--verbose'):
                if root_logger.getEffectiveLevel() == logging.INFO:
                    root_logger.setLevel(logging.VERBOSE)
                elif root_logger.getEffectiveLevel() == logging.VERBOSE:
                    root_logger.setLevel(logging.DEBUG)
            elif option in ('-h', '--help'):
                usage()
                return
            else:
                # Programming error...
                assert False, "Unhandled option!"
        # Handle the positional arguments.
        if len(arguments) < 2:
            usage()
            return
        supported_actions = ('start', 'commit', 'kill', 'delete')
        action = arguments.pop(0)
        if action not in supported_actions:
            msg = "Action not supported: %r (supported actions are: %s)"
            raise Exception, msg % (action, ', '.join(supported_actions))
    except Exception, e:
        logger.error("Failed to parse command line arguments!")
        logger.exception(e)
        usage()
        sys.exit(1)
    # Start the container and connect to it over SSH.
    try:
        for image_name in arguments:
            container = Container(image=Image.coerce(image_name),
                                  hostname=hostname)
            if action == 'start':
                container.start()
                if len(arguments) == 1 and all(os.isatty(n) for n in range(3)):
                    ssh_timer = Timer()
                    logger.info("Detected interactive terminal, connecting to container ..")
                    ssh_client = subprocess.Popen(['ssh', container.ssh_alias])
                    ssh_client.wait()
                    if ssh_client.returncode == 0:
                        logger.info("SSH client exited after %s.", ssh_timer)
                    else:
                        logger.warn("SSH client exited with status %i after %s.",
                                    ssh_client.returncode, ssh_timer)
            elif action == 'commit':
                container.commit(message=message)
            elif action == 'kill':
                container.kill()
            elif action == 'delete':
                container.delete()
            else:
                # Programming error...
                assert False, "Unhandled action!"
    except Exception, e:
        logger.exception(e)
        sys.exit(1)

def usage():
    """
    Print a usage message to the console.
    """
    print textwrap.dedent("""
        Usage: redock [OPTIONS] ACTION CONTAINER..

        Create and manage Docker containers and images. Supported actions are
        `start', `commit', `kill' and `delete'.

        Supported options:

          -n, --hostname=NAME  set container host name (defaults to image tag)
          -m, --message=TEXT   message for image created with `commit' action
          -v, --verbose        make more noise (can be repeated)
          -h, --help           show this message and exit
    """).strip()

# vim: ts=4 sw=4 et
