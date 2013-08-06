# Minimal configuration management specialized to Ubuntu (Debian).
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: August 6, 2013
# URL: https://github.com/xolox/python-redock

"""
Bootstrap is a minimal `configuration management`_ system. Right now it's just
a toy module that I may or may not use to extend Redock beyond the existing
``redock start``, ``redock commit`` and ``redock kill`` functionality and
commands. Here is the design rationale behind Bootstrap (in its current form):

**Specialized towards Debian**
  Bootstrap is specialized towards Debian Linux (and its derivatives) because I
  have several years of hands on experience with Debian and Ubuntu Linux and
  because Docker currently gravitates to Ubuntu Linux (although this will
  probably change over time).

**Based on SSH connections**
  SSH_ is used to connect to remote hosts because it's the lowest common
  denominator that works with Docker_, VirtualBox_, XenServer_ and physical
  servers while being secure and easy to use.

**Remote code execution using Python**
  The execnet_ package is used to execute Python code on remote systems because
  I prefer the structure of Python code over shell scripts (Python avoids
  `quoting hell`_). When Bootstrap connects to a remote system it automatically
  installs the system package ``python2.7`` on the remote system because this
  is required to run execnet_ (on the other hand, execnet_ itself does not have
  to be installed on the remote system).

.. _configuration management: http://en.wikipedia.org/wiki/Configuration_management#Operating_System_configuration_management
.. _Docker: http://www.docker.io/
.. _execnet: http://codespeak.net/execnet/
.. _quoting hell: http://wiki.tcl.tk/1726
.. _SSH: http://en.wikipedia.org/wiki/Secure_Shell
.. _VirtualBox: https://www.virtualbox.org/
.. _XenServer: http://www.xenserver.org/
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
from redock.logger import get_logger
from redock.utils import quote_command_line

MIRROR_FILE = os.path.expanduser('~/.redock/ubuntu-mirror.txt')

logger = get_logger(__name__)

class Bootstrap(object):

    """
    The Bootstrap configuration management system is implemented as the class
    :py:class:`Bootstrap`.
    """

    def __init__(self, ssh_alias):
        """
        Initialize the configuration management system by creating an execnet_
        gateway over an SSH connection. First we make sure the ``python2.7``
        package is installed; without it execnet_ won't work.

        :param ssh_alias: Alias of remote host in SSH client configuration.
        """
        self.logger = logger
        self.ssh_alias = ssh_alias
        # TODO Weaken requirement to just having "some version" of Python installed?
        self.logger.info("%s: Making sure the `python2.7' package is installed ..", self.ssh_alias)
        self.install_packages('python2.7')
        self.logger.info("%s: Initializing execnet over SSH connection ..", self.ssh_alias)
        # TODO Support sudo using makegateway('ssh=%s//python=sudo python')
        self.gateway = makegateway("ssh=%s" % self.ssh_alias)

    def upload_file(self, pathname, contents):
        """
        Create a file on the remote file system.

        :param pathname: The absolute pathname on the remote system.
        :param contents: The contents of the file (a string).
        """
        def remote_function(channel, pathname, contents):
            """
            Pure function that's executed remotely to create/update the file.
            """
            import os.path
            directory = os.path.dirname(pathname)
            if not os.path.isdir(directory):
                os.makedirs(directory)
            handle = open(pathname, 'w')
            handle.write(contents)
            bytes_written = handle.tell()
            handle.close()
            channel.send(bytes_written)
        channel = self.gateway.remote_exec(remote_function, pathname=pathname, contents=contents)
        bytes_written = channel.receive()
        if len(contents) != bytes_written:
            msg = "Remote side reported %i bytes written, but local side expected %i bytes!"
            raise Exception, msg % (bytes_written, len(contents))

    def install_packages(self, *packages):
        """
        Install the given system packages on the remote system.

        :param packages: The names of one or more packages to install (strings).
        """
        self.execute('apt-get', 'install', '-q', '-y', *packages)

    def update_system_packages(self):
        """
        Perform a full upgrade of all system packages on the remote system.
        """
        self.execute('apt-get', 'dist-upgrade', '-q', '-y', '--no-install-recommends')

    def execute(self, *command, **kw):
        """
        Execute a remote command over SSH so that the output of the remote
        command (the standard output and standard error streams) is immediately
        visible on the local terminal. If no standard input is given, this
        allocates a pseudo-tty_ (using ``ssh -t``) which means the operator can
        interact with the remote system should it prompt for input.

        Raises :py:exc:`ExternalCommandFailed` if the remote command ends with a
        nonzero exit code.

        :param command: A list with the remote command and its arguments.
        :param input: The standard input for the command (expected to be a
                      string). This is an optional keyword argument. If this
                      argument is given, no pseudo-tty_ will be allocated.

        .. _pseudo-tty: http://en.wikipedia.org/wiki/Pseudo_terminal
        """
        has_input = kw.get('input') is not None
        ssh_command = ['ssh']
        if not has_input:
            ssh_command.append('-t')
        ssh_command.append(self.ssh_alias)
        ssh_command.extend(command)
        self.logger.info("%s: Executing command %s", self.ssh_alias, ' '.join(ssh_command))
        options = dict()
        if has_input:
            options['stdin'] = subprocess.PIPE
        process = subprocess.Popen(ssh_command, **options)
        process.communicate(kw.get('input'))
        self.logger.debug("%s: Command exited with status %i.", self.ssh_alias, process.returncode)
        if process.returncode != 0:
            msg = "Remote command on %s failed with exit status %i! (command: %s)"
            raise ExternalCommandFailed, msg % (self.ssh_alias, process.returncode, ' '.join(command))

    def rsync(self, local_directory, remote_directory, cvs_exclude=True, delete=True):
        """
        Copy a directory on the host to the container using rsync over SSH.

        Raises :py:exc:`ExternalCommandFailed` if the remote command ends with a
        nonzero exit code.

        :param local_directory: The pathname of the source directory on the host.
        :param remote_directory: The pathname of the target directory in the container.
        :param cvs_exclude: Exclude version control files (enabled by default).
        :param delete: Delete remote files that don't exist locally (enabled by default).
        """
        rsync_timer = Timer()
        self.install_packages('rsync')
        def normalize(directory):
            """ Make sure a directory path ends with a trailing slash. """
            return "%s/" % directory.rstrip('/')
        location = "%s:%s" % (self.ssh_alias, normalize(remote_directory))
        self.logger.debug("Uploading %s to %s ..", local_directory, location)
        command = ['rsync', '-a']
        command.extend(['--rsync-path', 'mkdir -p %s && rsync' % pipes.quote(remote_directory)])
        if cvs_exclude:
            command.append('--cvs-exclude')
            command.extend(['--exclude', '.hgignore'])
        if delete:
            command.append('--delete')
        command.append(normalize(local_directory))
        command.append(location)
        self.logger.debug("Generated rsync command: %s", quote_command_line(command))
        exit_code = os.spawnvp(os.P_WAIT, command[0], command)
        if exit_code == 0:
            self.logger.debug("Finished upload using rsync in %s.", rsync_timer)
        self.logger.debug("rsync exited with status %d.", exit_code)
        if exit_code != 0:
            msg = "Failed to upload directory %s to %s, rsync exited with nonzero status %d! (command: %s)"
            raise ExternalCommandFailed, msg % (local_directory, location, exit_code, quote_command_line(command))

class ExternalCommandFailed(Exception):
    """
    Raised by :py:func:`Bootstrap.execute()` and :py:func:`Bootstrap.rsync()`
    when an external command fails (ends with a nonzero exit status).
    """

# vim: ts=4 sw=4 et
