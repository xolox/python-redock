# Minimal configuration management system specialized to Debian/Ubuntu/Docker.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 8, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import os
import pipes
import subprocess
import urllib

# External dependencies.
from execnet import makegateway
from humanfriendly import Timer

# Modules included in our package.
from redock.logger import logger
from redock.utils import quote_command_line

class Bootstrap(object):

    """
    :py:class:`Bootstrap` is a minimal configuration management system. The
    following points give a short summary of the goals I had in mind when I
    started writing it:

    - It's specialized towards Debian Linux (and its derivatives) because I
      have several years of hands on experience with Debian and Ubuntu Linux
      and because Docker currently gravitates to Ubuntu Linux (although this
      will probably change over time).

    - SSH is used to connect to remote hosts because it's the lowest common
      denominator that works with Docker, VirtualBox, XenServer and physical
      servers while being secure and easy to use.
    """

    def __init__(self, ssh_alias):
        """
        Initialize the configuration management system.

        :param ssh_alias: Alias of remote host in SSH client configuration.
        """
        self.logger = logger
        self.ssh_alias = ssh_alias
        self.initialize_execnet()

    def initialize_execnet(self):
        """
        Initialize the ``execnet`` gateway over an SSH connection. First we
        make sure the ``python2.7`` package is installed; without it
        ``execnet`` won't work.
        """
        self.logger.info("%s: Making sure the `python2.7' package is installed ..", self.ssh_alias)
        self.install_packages('python2.7')
        self.logger.info("%s: Initializing `execnet' connection ..", self.ssh_alias)
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
        self.execute('apt-get', 'install', '-q', '-y', '--no-install-recommends', *packages)

    def enable_package_repositories(self, *repositories):
        """
        Configure the remote package management system (``apt-get``) by
        overwriting ``/etc/apt/sources.list``. Picks a nearby Ubuntu package
        mirror and enables the given repositories (by default only the ``main``
        repository is enabled).

        :param names: The names of the package repositories to enable.
        """
        # By default only the main area is enabled.
        if not repositories:
            repositories = ('main',)
        self.logger.info("Enabling package repositories: %s", ' '.join(repositories))
        # Find an Ubuntu mirror that is geographically close to the current location.
        # TODO Pick a mirror once, remember in ~/.redock/mirror.txt?
        mirrors_txt = 'http://mirrors.ubuntu.com/mirrors.txt'
        self.logger.debug("Finding nearby Ubuntu package mirror using %s ..", mirrors_txt)
        mirror = urllib.urlopen(mirrors_txt).readline().strip()
        self.logger.debug("Selected mirror: %s", mirror)
        # Generate the contents of `/etc/apt/sources.list'.
        template = 'deb {mirror} {channel} {repositories}\n'
        repositories = ' '.join(repositories)
        lines = []
        for channel in ['precise', 'precise-updates', 'precise-backports', 'precise-security']:
            lines.append(template.format(mirror=mirror,
                                         channel=channel,
                                         repositories=repositories))
        self.upload_file('/etc/apt/sources.list', ''.join(lines))
        self.execute('apt-get', 'update')

    def update_system_packages(self, hold=('upstart', 'initscripts')):
        """
        Perform a full upgrade of all packages inside the container.
        """
        # https://help.ubuntu.com/community/PinningHowto#Introduction_to_Holding_Packages
        # TODO Document why these packages are on hold.
        try:
            self.logger.info("Marking packages on hold: %s", ' '.join(hold))
            self.execute('apt-mark', 'hold', *hold)
        except RemoteCommandFailed:
            self.logger.warn("Failed to hold packages, assuming it was done previously")
        self.execute('apt-get', 'dist-upgrade', '-q', '-y', '--no-install-recommends')

    def execute(self, *command, **kw):
        """
        Execute a remote command over SSH so that the output of the remote
        command is immediately visible on the local terminal.

        :param command: The command and its arguments.
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

    def set_default_locale(self):
        """
        The locale in Docker base images is not set up correctly, which causes
        various programs (like ``apt-get``) to continuously spit out warnings.
        This method reconfigures locale support to silence these warnings.
        """
        self.install_packages('language-pack-en-base')

class RemoteCommandFailed(Exception):
    """
    Custom exception raised by :py:func:`Bootstrap.execute()` when a remote
    command fails (exits with a nonzero exit status).
    """

# vim: ts=4 sw=4 et
