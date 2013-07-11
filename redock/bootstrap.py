# Minimal configuration management specialized to Ubuntu (Debian).
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 12, 2013
# URL: https://github.com/xolox/python-redock

"""
Bootstrap is a *minimal* `configuration management`_ system. Here are the goals
(constraints) I had in mind when I started working on Bootstrap:

**Specialized towards Debian**
  Bootstrap is specialized towards Debian Linux (and its derivatives) because I
  have several years of hands on experience with Debian and Ubuntu Linux and
  because Docker currently gravitates to Ubuntu Linux (although this will
  probably change over time).

**Based on SSH connections**
  SSH_ is used to connect to remote hosts because it's the lowest common
  denominator that works with Docker, VirtualBox, XenServer and physical
  servers while being secure and easy to use.

.. _configuration management: http://en.wikipedia.org/wiki/Configuration_management#Operating_System_configuration_management
.. _SSH: http://en.wikipedia.org/wiki/Secure_Shell
"""

# Standard library modules.
import os
import os.path
import pipes
import subprocess

# External dependencies.
from execnet import makegateway
from humanfriendly import Timer

# Modules included in our package.
from redock.logger import logger
from redock.utils import quote_command_line

MIRROR_FILE = os.path.expanduser('~/.redock/ubuntu-mirror.txt')

class Bootstrap(object):

    #"""
    #The Bootstrap configuration management system is implemented as the class
    #:py:class:`Bootstrap`. The constructor takes one argument: the SSH alias of
    #a remote host as defined in your `~/.ssh/config`.
    #"""

    def __init__(self, ssh_alias):
        """
        Initialize the configuration management system by creating an
        ``execnet`` gateway over an SSH connection. First we make sure the
        ``python2.7`` package is installed; without it ``execnet`` won't
        work.

        :param ssh_alias: Alias of remote host in SSH client configuration.
        """
        self.logger = logger
        self.ssh_alias = ssh_alias
        self.logger.info("%s: Making sure the `python2.7' package is installed ..", self.ssh_alias)
        self.install_packages('python2.7')
        self.logger.info("%s: Initializing execnet over SSH connection ..", self.ssh_alias)
        self.gateway = makegateway("ssh=%s" % self.ssh_alias)

    def upload_file(self, pathname, contents):
        """
        Create a file on the container's file system.

        :param pathname: The absolute pathname in the container.
        :param contents: The contents of the file (a string).
        """
        # Pure function that's executed remotely.
        def remote_function(channel, pathname, contents):
            import os.path
            directory = os.path.dirname(pathname)
            if not os.path.isdir(directory):
                os.makedirs(directory)
            handle = open(pathname, 'w')
            handle.write(contents)
            handle.close()
        self.gateway.remote_exec(remote_function, pathname=pathname, contents=contents)

    def install_packages(self, *packages):
        """
        Install the given system packages inside the container.

        :param packages: The names of one or more packages to install (strings).
        """
        self.execute('apt-get', 'install', '-q', '-y', *packages)

    def update_system_packages(self):
        """
        Perform a full upgrade of all system packages inside the container.
        """
        self.execute('apt-get', 'dist-upgrade', '-q', '-y', '--no-install-recommends')

    def execute(self, *command, **kw):
        """
        Execute a remote command over SSH so that the output of the remote
        command is immediately visible on the local terminal.

        :param command: The command and its arguments.
        :param input: The standard input for the command (a string).
        """
        command = ['ssh', '-t', self.ssh_alias] + list(command)
        self.logger.info("%s: Executing command %s", self.ssh_alias, ' '.join(command))
        options = dict()
        if kw.get('input') is not None:
            options['stdin'] = subprocess.PIPE
        process = subprocess.Popen(command, **options)
        process.communicate(kw.get('input'))
        self.logger.debug("%s: Command exited with status %i.", self.ssh_alias, process.returncode)
        if process.returncode != 0:
            msg = "Remote command failed with exit status %i! (command: %s)"
            raise RemoteCommandFailed, msg % (process.returncode, ' '.join(command))

    def rsync(self, host_directory, container_directory, cvs_exclude=True):
        """
        Copy a directory on the host to the container using rsync over SSH.

        :param host_directory: The pathname of the source directory on the host.
        :param container_directory: The pathname of the target directory in the container.
        :param cvs_exclude: Exclude version control files (enabled by default).
        """
        rsync_timer = Timer()
        self.install_packages('rsync')
        def normalize(directory):
            """ Make sure a directory path ends with a trailing slash. """
            return "%s/" % directory.rstrip('/')
        location = "%s:%s" % (self.ssh_alias, normalize(container_directory))
        self.logger.debug("Uploading %s to %s ..", host_directory, location)
        command = ['rsync', '-a', '--delete']
        command.extend(['--rsync-path', 'mkdir -p %s && rsync' % pipes.quote(container_directory)])
        if cvs_exclude:
            command.append('--cvs-exclude')
            command.extend(['--exclude', '.hgignore'])
        command.append(normalize(host_directory))
        command.append(location)
        self.logger.debug("Generated rsync command: %s", quote_command_line(command))
        exit_code = os.spawnvp(os.P_WAIT, command[0], command)
        if exit_code == 0:
            self.logger.debug("Finished upload using rsync in %s.", rsync_timer)
        self.logger.debug("rsync exited with status %d.", exit_code)
        if exit_code != 0:
            msg = "Failed to upload directory %s to %s, rsync exited with nonzero status %d! (command: %s)"
            raise RemoteCommandFailed, msg % (host_directory, location, exit_code, quote_command_line(command))

class RemoteCommandFailed(Exception):
    """
    Raised by :py:func:`Bootstrap.execute()` when a remote
    command fails (exits with a nonzero exit status).
    """

# vim: ts=4 sw=4 et
