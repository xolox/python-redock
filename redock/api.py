# Human friendly wrapper around Docker.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 9, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import os
import pipes
import socket
import subprocess
import sys
import textwrap
import time

# External dependencies.
import docker
import humanfriendly
import update_dotdee

# Initialize the logger.
from redock.logger import logger
from redock.utils import (apt_get_install, find_local_ip_addresses,
                          quote_command_line, slug, summarize_id)

# The default base image for new containers.
DEFAULT_BASE_IMAGE = 'ubuntu:precise'

# Directory with generated SSH key pairs on the host.
SSH_KEY_CATALOG = os.path.expanduser('~/.redock/ssh')

class Container(object):

    """
    The :py:class:`Container` class is the main entry point to the Redock API.
    It aims to provide a simple to use representation of Docker containers.
    You'll probably never need most of the methods defined in this class; if
    you're getting started with Redock you should focus on these methods:

    - :py:func:`Container.start()`
    - :py:func:`Container.commit()`
    - :py:func:`Container.kill()`

    After you create and start a container with Redock you can do with the
    container what you want by starting out with an SSH connection. When you're
    done you either save your changes or discard them and kill the container.
    That's probably all you need from Redock :-)
    """

    def __init__(self, image, base=DEFAULT_BASE_IMAGE, hostname=None, timeout=10):
        """
        Initialize a :py:class:`Container` instance from the given arguments.

        :param image: The repository and tag of the container's image (in the
                      format expected by :py:class:`Image.coerce()`).
        :param base: The repository and tag of the base image for the container
                     (in the format expected by :py:class:`Image.coerce()`).
        :param hostname: The host name to use inside the container.
        :param timeout: The timeout while waiting for a container to become
                        reachable over SSH.
        """
        # Validate and store the arguments.
        self.image = Image.coerce(image)
        self.base = Image.coerce(base)
        self.hostname = hostname or self.image.tag
        self.timeout = timeout
        # Initialize some private variables.
        self.logger = logger
        self.session = Session()
        self.update_dotdee = update_dotdee.UpdateDotDee(os.path.expanduser('~/.ssh/config'))
        # Connect to the Docker API over HTTP.
        try:
            self.logger.debug("Connecting to Docker daemon ..")
            self.docker = docker.Client()
            self.logger.debug("Successfully connected to Docker.")
        except Exception, e:
            self.logger.error("Failed to connect to Docker!")
            self.logger.exception(e)
            raise

    def start(self):
        """
        Create and start the Docker container:

        1. Download the base image using
           :py:func:`Container.download_base_image()` (only if needed).
        2. Install and configure an SSH server and install a generated SSH
           private key using :py:func:`Container.install_ssh_server()` (only if
           needed).
        3. Start the SSH server using
           :py:func:`Container.start_ssh_server()`.
        4. Configure SSH access to the container using
           :py:func:`Container.setup_ssh_access()`.
        5. Wait for the container to become reachable over SSH.
        """
        if not self.find_running_container():
            if not self.find_custom_image():
                self.logger.info("Image doesn't exist yet, creating it: %r", self.image)
                self.download_base_image()
                self.install_ssh_server()
                self.start_ssh_server()
            else:
                self.start_ssh_server()
        self.setup_ssh_access()

    def kill(self):
        """
        Kill and delete the container. All changes  since the last time that
        :py:func:`Container.commit()` was called will be lost.
        """
        if self.find_running_container():
            self.detach()
            self.logger.info("Killing container ..")
            self.docker.kill(self.session.container_id)
            self.logger.info("Removing container ..")
            self.docker.remove_container(self.session.container_id)
            self.session.reset()
        self.revoke_ssh_access()

    def attach(self):
        """
        Attach to the running Docker container in a subprocess so that the user
        can see the output of whatever is happening inside the container on
        their terminal. This is similar to the ``docker attach`` command except
        it does not open an interactive terminal.

        Automatically called by :py:func:`Container.fork_command()`
        so the user gets to see the output of the command that was started.

        Raises :py:class:`NoContainerRunning` if an associated Docker container
        is not already running.
        """
        self.check_container_active()
        if not self.session.remote_terminal:
            self.logger.verbose("Attaching to container's terminal using command: docker attach %s",
                                summarize_id(self.session.container_id))
            self.session.remote_terminal = subprocess.Popen(['docker', 'attach', self.session.container_id],
                                                            stdin=open(os.devnull),
                                                            stdout=sys.stderr)

    def detach(self):
        """
        Detach from the running container. This kills the subprocess that
        relays the output from the container. It is not an error if
        :py:func:`Container.attach()` was not previously called.

        Automatically called by :py:func:`Container.kill()`.
        """
        if self.session.remote_terminal:
            if self.session.remote_terminal.poll() is None:
                self.session.remote_terminal.kill()
            self.session.remote_terminal = None

    def find_running_container(self):
        """
        Check to see if the current :py:class:`Container` has an associated
        Docker container that is currently running.

        :returns: ``True`` when a running container exists, ``False``
                  otherwise.
        """
        if not self.session.container_id:
            self.logger.info("Looking for running container ..")
            for container in self.docker.containers():
                if container.get('Image') == self.image.name:
                    self.session.container_id = container['Id']
                    self.logger.info("Found running container: %s",
                                     summarize_id(self.session.container_id))
        return bool(self.session.container_id)

    def find_custom_image(self):
        """
        Look for an existing image belonging to the container (i.e. an image
        with the repository and tag specified as the ``name`` argument to the
        constructor of :py:class:`Container`).

        :returns: An :py:class:`Image` instance if an existing image is found,
                  ``None`` otherwise.
        """
        if not self.session.custom_image:
            self.logger.debug("Looking for existing image: %r", self.image)
            self.session.custom_image = self.find_named_image(self.image)
            if self.session.custom_image:
                self.logger.debug("Found existing image: %r", self.session.custom_image)
            else:
                self.logger.debug("No existing image found.")
        return self.session.custom_image

    def download_base_image(self):
        """
        Download the base image required to create the container. Uses the base
        image specified in the constructor of :py:class:`Container`. If the
        base image is not available yet it is assumed to be a public image. If
        the base image is already available locally it won't be downloaded
        again.

        Automatically called by :py:func:`Container.start()` as needed.
        """
        self.logger.verbose("Looking for existing base image of %s ..", self.image)
        if not self.find_named_image(self.base):
            download_timer = humanfriendly.Timer()
            self.logger.info("Downloading base image (please be patient): %s", self.base)
            self.docker.pull(repository=self.base.repository, tag=self.base.tag)
            self.logger.info("Finished downloading base image in %s.", download_timer)

    def find_named_image(self, image_to_find):
        """
        Find the most recent Docker image with the given repository and tag.

        :param image_to_find: The :py:class:`Image` we're looking for.
        :returns: The most recent :py:class:`Image` available, or ``None`` if
                  no images were matched.
        """
        matches = []
        for image in self.docker.images():
            if (image.get('Repository') == image_to_find.repository
                    and image.get('Tag') == image_to_find.tag):
                matches.append(image)
        if matches:
            matches.sort(key=lambda i: i['Created'])
            image = matches[-1]
            return Image(repository=image['Repository'],
                         tag=image['Tag'],
                         id=image['Id'])

    def install_ssh_server(self):
        """
        Install and configure an SSH server (the package ``openssh-server``)
        and install a generated SSH public key inside the running Docker
        container. Because this method is Redock's first exposure to fresh
        containers it will perform some miscellaneous tasks to initialize a
        base image:

        - Out of the box a lot of commands in Docker containers spit out
          obnoxious warnings about the locale. Installing the
          ``language-pack-en-base`` package resolves the problem.

        - The ``initscripts`` and ``upstart`` packages are set on hold, so that
          ``apt-get dist-upgrade`` doesn't try to upgrade these packages (doing
          so will result in errors).

        Called by :py:func:`Container.start()`.
        """
        install_timer = humanfriendly.Timer()
        commands = []
        # TODO Document why these packages are on hold.
        # https://help.ubuntu.com/community/PinningHowto#Introduction_to_Holding_Packages
        commands.append('apt-mark hold initscripts upstart')
        commands.append(apt_get_install('language-pack-en-base', 'openssh-server'))
        commands.append('mkdir -p /root/.ssh')
        commands.append('echo %s > /root/.ssh/authorized_keys' % pipes.quote(self.get_ssh_public_key()))
        self.wait_for_command(' && '.join(commands))
        self.commit(message="Installed SSH server & public key")
        self.logger.info("Installed SSH server in %s.", install_timer)

    def start_ssh_server(self):
        """
        Starts the container and runs an SSH server inside the container.

        We have to start the SSH server ourselves because Docker replaces
        ``/sbin/init`` inside the container, which means ``sshd`` is not
        managed by upstart. Also Docker works on the principle of running some
        main application in the foreground; in our case it will be ``sshd``.

        In the future Redock might be changed to use e.g. Supervisor, but for
        now ``sshd`` will do just fine :-)
        """
        self.logger.info("Starting SSH server ..")
        command_line = 'mkdir -p -m0755 /var/run/sshd && /usr/sbin/sshd -eD'
        self.fork_command(command_line)

    def get_ssh_client_command(self, ip_address=None, port_number=None):
        """
        Generate an SSH client command line that connects to the container
        (assumed to be running).

        :param ip_address: This optional argument overrides the default IP
                           address (which is otherwise automatically
                           discovered).
        :param port_number: This optional argument overrides the default port
                            number (which is otherwise automatically
                            discovered).
        :returns: The SSH client command line as a list of strings containing
                  the command and its arguments.
        """
        command = ['ssh']
        # Connect as the root user inside the container.
        command.extend(['-l', 'root'])
        # Connect using the generated SSH private key.
        command.extend(['-i', self.get_ssh_private_key_file()])
        # Don't check or store the host key (it's pointless).
        command.extend(['-o', 'StrictHostKeyChecking=no'])
        command.extend(['-o', 'UserKnownHostsFile=/dev/null'])
        # Silence the message "Warning: Permanently added ... to the list of known hosts."
        command.append('-q')
        # Connect through a NAT port on the local system.
        if not (ip_address and port_number):
            ip_address, port_number = self.ssh_endpoint
        command.extend(['-p', str(port_number)])
        # Make the SSH connection binary safe.
        command.extend(['-e', 'none'])
        # Finish the command by including the IP address.
        command.append(ip_address)
        self.logger.debug("Generated SSH command: %s", quote_command_line(command))
        # Return the generated command.
        return command

    @property
    def ssh_alias(self):
        """
        Get the SSH alias that should be used to connect to the container.
        """
        return slug(self.hostname + '-container')

    def setup_ssh_access(self):
        """
        Update ``~/.ssh/config`` to include a host definition that makes it
        easy to connect to the container over SSH from the host system.
        """
        self.logger.verbose("Configuring SSH access ..")
        with open(self.ssh_config_file, 'w') as handle:
            handle.write(textwrap.dedent("""
                Host {alias}
                  Hostname {address}
                  Port {port}
                  User root
                  IdentityFile {key}
                  StrictHostKeyChecking no
                  UserKnownHostsFile /dev/null
            """.format(alias=self.ssh_alias,
                       address=self.ssh_endpoint[0],
                       port=self.ssh_endpoint[1],
                       key=self.get_ssh_private_key_file(),
                       redock=pipes.quote(os.path.abspath(sys.argv[0])),
                       container=pipes.quote(self.image.name))))
        self.update_dotdee.update_file()
        self.logger.info("Successfully configured SSH access. Use this command: ssh %s", self.ssh_alias)

    def revoke_ssh_access(self):
        """
        Remove the container's SSH client configuration from
        ``~/.ssh/config``.
        """
        self.logger.info("Removing SSH client configuration ..")
        if os.path.isfile(self.ssh_config_file):
            os.unlink(self.ssh_config_file)
        self.update_dotdee.update_file()

    @property
    def ssh_config_file(self):
        """
        Get the pathname of the SSH client configuration for the container.
        """
        return os.path.expanduser('~/.ssh/config.d/redock:%s' % self.image.name)

    @property
    def ssh_endpoint(self):
        """
        Wait for the container to become reachable over SSH and get a tuple
        with the IP address and port number that can be used to connect to the
        container over SSH.
        """
        self.check_container_active()
        if self.session.ssh_endpoint:
            return self.session.ssh_endpoint
        # Get the local port connected to the container.
        host_port = int(self.docker.port(self.session.container_id, '22'))
        self.logger.debug("Configured port redirection for container %s: %s:%i -> %s:%i",
                          summarize_id(self.session.container_id),
                          socket.gethostname(), host_port,
                          self.hostname, 22)
        # Give the container time to finish the SSH server installation.
        self.logger.verbose("Waiting for SSH connection to %s (max %i seconds) ..",
                            summarize_id(self.session.container_id), self.timeout)
        global_timeout = time.time() + self.timeout
        ssh_timer = humanfriendly.Timer()
        while time.time() < global_timeout:
            for ip_address in find_local_ip_addresses():
                # Try to open an SSH connection to the container.
                self.logger.debug("Connecting to container over SSH at %s:%s ..", ip_address, host_port)
                command = self.get_ssh_client_command(ip_address, host_port) + ['true']
                ssh_client = subprocess.Popen(command, stdin=open(os.devnull), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # Give this attempt at most 10 seconds to succeed.
                inner_timeout = time.time() + 10
                while time.time() < inner_timeout:
                    if ssh_client.poll() is not None:
                        break
                    time.sleep(0.1)
                else:
                    self.logger.debug("Attempt to connect timed out!")
                if ssh_client.returncode == 0:
                    # At this point we have successfully connected!
                    self.session.ssh_endpoint = (ip_address, host_port)
                    self.logger.debug("Connected to %s at %s using SSH in %s.",
                                      self.image.name, self.session.ssh_endpoint,
                                      ssh_timer)
                    return self.session.ssh_endpoint
                time.sleep(1)
        msg = "Time ran out while waiting to connect to container %s over SSH! (Most likely something went wrong while initializing the container..)"
        raise SecureShellTimeout, msg % self.image.name

    def wait_for_command(self, command):
        """
        Create the container, start it, run the given command and wait for the
        command to finish.

        :param command: The Bash command line to execute inside the container
                        (a string).
        """
        self.fork_command(command)
        self.docker.wait(self.session.container_id)

    def fork_command(self, command):
        """
        Create and start a Docker container, fork the given command inside the
        container and return control to the caller without waiting for the
        command inside the container to finish. If an existing image exists for
        the container, it will be used to start the container. Otherwise the
        base image is used.

        :param command: The Bash command line to execute inside the container
                        (a string).
        """
        # TODO Should we make sure the container is not already running?
        # TODO Make the port numbers configurable?
        # Find the image to use as a base for the container.
        image = self.find_custom_image() or self.find_named_image(self.base)
        self.logger.debug("Creating container from image: %r", image)
        # Start the container with the given command.
        result = self.docker.create_container(image=image.unique_name,
                                              command='bash -c %s' % pipes.quote(command),
                                              hostname=self.hostname,
                                              ports=['22'])
        # Remember and report the container id.
        self.session.container_id = result['Id']
        self.logger.debug("Created container: %s", summarize_id(self.session.container_id))
        # Start the command inside the container.
        self.logger.debug("Running command: %s", command)
        self.docker.start(self.session.container_id)
        # Make sure the user sees all output from the container.
        self.attach()

    def commit(self, message=None, author=None):
        """
        Commit any changes to the running container. Corresponds to the
        ``docker commit`` command.

        Raises :py:class:`NoContainerRunning` if an associated Docker container
        is not already running.

        :param message: A short message describing the commit (a string).
        :param author: The name of the author (a string).
        """
        self.check_container_active()
        self.logger.verbose("Committing changes: %s", message or 'no description given')
        self.docker.commit(self.session.container_id, repository=self.image.repository,
                           tag=self.image.tag, message=message, author=author)
        self.kill()
        self.start()

    def __repr__(self):
        """
        Pretty print a :py:class:`Container` object.
        """
        template = "Container(image=%r, base=%r, hostname=%r)"
        return template % (self.image, self.base, self.hostname)

    def get_ssh_private_key_file(self):
        """
        Get the pathname of the SSH private key associated with the container.
        """
        return os.path.join(SSH_KEY_CATALOG, self.image.name)

    def get_ssh_public_key(self):
        """
        Get the contents of the SSH public key associated with the container.
        If the container doesn't have an associated SSH key pair yet, it will
        be generated first using :py:func:`Container.generate_ssh_key_pair()`.
        """
        public_key_file = os.path.join(SSH_KEY_CATALOG, '%s.pub' % self.image.name)
        if not os.path.isfile(public_key_file):
            self.generate_ssh_key_pair()
        with open(public_key_file) as handle:
            return handle.read().strip()

    def generate_ssh_key_pair(self):
        """
        Generate an SSH key pair for communication between the host system and
        the Docker container. Requires the ``ssh-keygen`` program.

        Raises :py:class:`FailedToGenerateKey` if ``ssh-keygen`` fails.
        """
        self.logger.verbose("Checking if we need to generate a new SSH key pair ..")
        if not os.path.isdir(SSH_KEY_CATALOG):
            os.makedirs(SSH_KEY_CATALOG)
        private_key_file = self.get_ssh_private_key_file()
        if os.path.isfile(private_key_file):
            self.logger.verbose("SSH key pair was previously generated: %s", private_key_file)
        else:
            self.logger.info("No existing SSH key pair found, generating new pair: %s", private_key_file)
            command = ['ssh-keygen', '-t', 'rsa', '-f', private_key_file, '-N', '', '-C', 'root@%s' % self.hostname]
            ssh_keygen = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = ssh_keygen.communicate(input='')
            if ssh_keygen.returncode != 0:
                msg = "Failed to generate SSH key pair! (command exited with nonzero exit code %d: %r)"
                raise FailedToGenerateKey, msg % (ssh_keygen.returncode, command)

    # Miscellaneous methods.

    def check_container_active(self):
        """
        Check if the :py:class:`Container` is associated with a running Docker
        container. If no running Docker container is found,
        :py:class:`NoContainerRunning` is raised.
        """
        if not (self.session.container_id or self.find_running_container()):
            raise NoContainerRunning, "No active container!"

class Image(object):

    """
    Simple representation of Docker images.
    """

    def __init__(self, repository, tag, id=None):
        """
        Initialize an :py:class:`Image` instance from the given arguments.

        :param repository: The name of the image's repository.
        :param tag: The image's tag (name).
        :param id: The unique hash of the image (optional).
        """
        self.repository = repository
        self.tag = tag
        self.id = id

    @staticmethod
    def coerce(value):
        """
        Coerce strings to :py:class:`Image` objects.

        Raises :py:class:`ValueError` when a string with an incorrect format is
        given.

        :param value: The name of the image, expected to be a string of the
                      form ``repository:tag``. If an :py:class:`Image` object
                      is given it is returned unmodified.
        :returns: An :py:class:`Image` object.
        """
        if isinstance(value, basestring):
            components = value.split(':')
            if len(components) == 1:
                value = Image(repository=os.environ['USER'],
                              tag=components[0])
            else:
                if len(components) != 2:
                    msg = "Invalid image name (expected 'repository:tag', got %r)"
                    raise ValueError, msg % value
                value = Image(repository=components[0],
                              tag=components[1])
        return value

    @property
    def name(self):
        """
        Get the human readable name of an :py:class:`Image` as a string of the
        form ``repository:tag``.
        """
        return "%s:%s" % (self.repository, self.tag)

    @property
    def unique_name(self):
        """
        Get the machine readable unique name of an :py:class:`Image`. If the
        image has a unique hash that will be used, otherwise a string of the
        form ``repository:tag`` is returned.
        """
        if self.id:
            return self.id
        else:
            return self.name

    def __repr__(self):
        """
        Provide a textual representation of an :py:class:`Image` object.
        """
        properties = ["repository=%r" % self.repository,
                      "tag=%r" % self.tag]
        if self.id:
            properties.append("id=%r" % summarize_id(self.id))
        return "Image(%s)" % ", ".join(properties)

class Session(object):

    def __init__(self):
        self.reset()

    def reset(self):
        self.container_id = None
        self.custom_image = None
        self.remote_terminal = None
        self.ssh_endpoint = None

class SecureShellTimeout(Exception):
    """
    Custom exception raised by :py:func:`Container.ssh_endpoint` when Redock
    fails to connect to the Docker container within a reasonable amount of
    time.
    """

class FailedToGenerateKey(Exception):
    """
    Custom exception raised by :py:func:`Container.generate_ssh_key_pair()`
    when the ``ssh-keygen`` program fails to generate an SSH key pair.
    """

class NoContainerRunning(Exception):
    """
    Custom exception raised by :py:func:`Container.check_container_active`
    when a :py:class:`Container` doesn't have an associated Docker container
    running.
    """

# vim: ts=4 sw=4 et
