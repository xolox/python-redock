# Main API for Redock, a human friendly wrapper around Docker.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 16, 2013
# URL: https://github.com/xolox/python-redock

"""
The :py:mod:`redock.api` module defines two classes and two exception types:

- :py:class:`Container`
- :py:class:`Image`
- :py:class:`NoContainerRunning`
- :py:class:`SecureShellTimeout`
"""

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
from redock.logger import get_logger
from redock.base import BASE_IMAGE_NAME, find_base_image
from redock.utils import (PRIVATE_SSH_KEY, Config, RemoteTerminal,
                          find_local_ip_addresses, quote_command_line,
                          slug, summarize_id)

logger = get_logger(__name__)

class Container(object):

    """
    :py:class:`Container` is the main entry point to the Redock API. It aims to
    provide a simple to use representation of Docker containers (and in
    extension Docker images). You'll probably never need most of the methods
    defined in this class; if you're getting started with Redock you should
    focus on these methods:

    - :py:func:`Container.start()`
    - :py:func:`Container.commit()`
    - :py:func:`Container.kill()`

    After you create and start a container with Redock you can do with the
    container what you want by starting out with an SSH_ connection. When
    you're done you either save your changes or discard them and kill the
    container. That's probably all you need from Redock :-)

    .. _SSH: http://en.wikipedia.org/wiki/Secure_Shell
    """

    def __init__(self, image, hostname=None, timeout=10):
        """
        Initialize a :py:class:`Container` from the given arguments.

        :param image: The repository and tag of the container's image (in the
                      format expected by :py:class:`Image.coerce()`).
        :param hostname: The host name to use inside the container. If none is
                         given, the image's tag is used.
        :param timeout: The timeout in seconds while waiting for a container to
                        become reachable over SSH_ (a couple of seconds should
                        be plenty).
        """
        # Validate and store the arguments.
        self.image = Image.coerce(image)
        self.base = Image.coerce(BASE_IMAGE_NAME)
        self.hostname = hostname or self.image.tag
        self.timeout = timeout
        # Initialize some private variables.
        self.logger = logger
        self.config = Config()
        self.session = Session()
        self.update_dotdee = update_dotdee.UpdateDotDee(os.path.expanduser('~/.ssh/config'))
        # Connect to the Docker API over HTTP.
        try:
            self.logger.debug("Connecting to Docker daemon ..")
            self.client = docker.Client()
            self.logger.debug("Successfully connected to Docker.")
        except Exception, e:
            self.logger.error("Failed to connect to Docker!")
            self.logger.exception(e)
            raise

    def start(self):
        """
        Create and start the Docker container. On the first run of Redock this
        creates a base image using :py:func:`redock.base.create_base_image()`.
        """
        if not self.find_container():
            if not self.find_image(self.image):
                self.logger.info("Image doesn't exist yet, creating it: %r", self.image)
                self.base.id = find_base_image(self.client)
            self.start_supervisor()
        self.setup_ssh_access()

    def commit(self, message=None, author=None):
        """
        Commit any changes to the running container to the associated image.
        Corresponds to the ``docker commit`` command.

        Raises :py:exc:`NoContainerRunning` if an associated Docker container
        is not already running.

        :param message: A short message describing the commit (a string).
        :param author: The name of the author (a string).
        """
        self.check_active()
        self.logger.info("Committing changes: %s", message or 'no description given')
        result = self.client.commit(self.session.container_id, repository=self.image.repository,
                                    tag=self.image.tag, message=message, author=author)
        image_ids = [i['Id'] for i in self.client.images()]
        self.image.id = self.expand_id(result['Id'], image_ids)

    def kill(self):
        """
        Kill and remove the container. All changes since the last time that
        :py:func:`Container.commit()` was called will be lost.
        """
        if self.find_container():
            if self.session.remote_terminal:
                self.session.remote_terminal.detach()
            self.logger.info("Killing container ..")
            self.client.kill(self.session.container_id)
            self.logger.info("Removing container ..")
            self.client.remove_container(self.session.container_id)
            with self.config as state:
                del state['containers'][self.image.key]
            self.session.reset()
        self.revoke_ssh_access()

    def delete(self):
        """
        Delete the image associated with the container (if any). The data in
        the image will be lost.
        """
        self.logger.info("Deleting image %s ..", self.image.name)
        self.client.remove_image(self.image.name)

    def find_container(self):
        """
        Check to see if the current :py:class:`Container` has an associated
        Docker container that is currently running.

        :returns: ``True`` when a running container exists, ``False``
                  otherwise.
        """
        if not self.session.container_id:
            self.logger.verbose("Looking for running container ..")
            state = self.config.load()
            container_id = state['containers'].get(self.image.key)
            # Make sure the container is still running.
            if container_id in [c['Id'] for c in self.client.containers()]:
                self.session.container_id = container_id
                self.logger.info("Found running container: %s", summarize_id(container_id))
        return bool(self.session.container_id)

    def find_image(self, image_to_find):
        """
        Find the most recent Docker image with the given repository and tag.

        :param image_to_find: The :py:class:`Image` we're looking for.
        :returns: The most recent :py:class:`Image` available, or ``None`` if
                  no images were matched.
        """
        matches = []
        for image in self.client.images():
            if (image.get('Repository') == image_to_find.repository
                    and image.get('Tag') == image_to_find.tag):
                matches.append(image)
        if matches:
            matches.sort(key=lambda i: i['Created'])
            image = matches[-1]
            return Image(repository=image['Repository'],
                         tag=image['Tag'],
                         id=image['Id'])

    def start_supervisor(self):
        """
        Starts the container and runs Supervisor inside the container.
        """
        command = '/usr/bin/supervisord -n'
        self.logger.info("Starting process supervisor (and SSH server) ..")
        # Select the Docker image to use as a base for the container.
        image = self.find_image(self.image) or self.find_image(self.base)
        self.logger.verbose("Creating container from image: %r", image)
        # Start the container with the given command.
        result = self.client.create_container(image=image.unique_name,
                                              command=command,
                                              hostname=self.hostname,
                                              ports=['22'])
        container_ids = [c['Id'] for c in self.client.containers(all=True)]
        self.session.container_id = self.expand_id(result['Id'], container_ids)
        self.logger.verbose("Created container: %s", summarize_id(self.session.container_id))
        for text in result.get('Warnings', []):
            logger.warn("%s", text)
        # Start the command inside the container.
        self.logger.verbose("Running command: %s", command)
        self.client.start(self.session.container_id)
        # Make the output from the container visible to the user.
        self.session.remote_terminal = RemoteTerminal(self.session.container_id)
        self.session.remote_terminal.attach()
        # Persist association between (repository, tag) and container id.
        with self.config as state:
            state['containers'][self.image.key] = self.session.container_id

    def get_ssh_client_command(self, ip_address=None, port_number=None):
        """
        Generate an SSH_ client command line that connects to the container
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
        command.extend(['-i', PRIVATE_SSH_KEY])
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
        Get the SSH_ alias that should be used to connect to the container.
        """
        return slug(self.hostname + '-container')

    def setup_ssh_access(self):
        """
        Update ``~/.ssh/config`` to make it easy to connect to the container
        over SSH_ from the host system. This generates a host definition to
        include in the SSH client configuration file and uses update-dotdee_ to
        merge the generated host definition with the user's existing SSH client
        configuration file.

        .. _update-dotdee: https://pypi.python.org/pypi/update-dotdee
        """
        self.logger.verbose("Configuring SSH access ..")
        self.update_dotdee.create_directory()
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
                       key=PRIVATE_SSH_KEY,
                       redock=pipes.quote(os.path.abspath(sys.argv[0])),
                       container=pipes.quote(self.image.name))))
        self.update_dotdee.update_file()
        self.logger.info("Successfully configured SSH access. Use this command: ssh %s", self.ssh_alias)

    def revoke_ssh_access(self):
        """
        Remove the container's SSH_ client configuration from
        ``~/.ssh/config``.
        """
        self.logger.info("Removing SSH client configuration ..")
        if os.path.isfile(self.ssh_config_file):
            os.unlink(self.ssh_config_file)
        self.update_dotdee.update_file()

    @property
    def ssh_config_file(self):
        """
        Get the pathname of the SSH_ client configuration for the container.
        """
        return os.path.expanduser('~/.ssh/config.d/redock:%s' % self.image.name)

    @property
    def ssh_endpoint(self):
        """
        Wait for the container to become reachable over SSH_ and get a tuple
        with the IP address and port number that can be used to connect to the
        container over SSH.
        """
        self.check_active()
        if self.session.ssh_endpoint:
            return self.session.ssh_endpoint
        # Get the local port connected to the container.
        host_port = int(self.client.port(self.session.container_id, '22'))
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

    def __repr__(self):
        """
        Pretty print a :py:class:`Container` object.
        """
        template = "Container(image=%r, base=%r, hostname=%r)"
        return template % (self.image, self.base, self.hostname)

    # Miscellaneous methods.

    def check_active(self):
        """
        Check if the :py:class:`Container` is associated with a running Docker
        container. If no running Docker container is found,
        :py:class:`NoContainerRunning` is raised.
        """
        if not self.find_container():
            raise NoContainerRunning, "No active container!"

    def expand_id(self, short_id, candidate_ids):
        """
        :py:func:`docker.Client.create_container()` and
        :py:func:`docker.Client.commit()` report short ids (12 characters)
        while :py:func:`docker.Client.containers()` and
        :py:func:`docker.Client.images()` report long ids (65 characters). I'd
        rather use the full ids where possible. This method translates short
        ids into long ids at the expense of an additional API call (who
        cares).

        Raises :py:exc:`exceptions.Exception` if no long id corresponding to
        the short id can be matched (this might well be a purely theoretical
        problem, it certainly shouldn't happen during regular use).

        :param short_id: A short id of 12 characters.
        :param candidate_ids: A list of available long ids.
        :returns: The long id corresponding to the given short id.
        """
        self.logger.debug("Translation short id %s into long id ..", short_id)
        for long_id in candidate_ids:
            self.logger.debug("Checking candidate: %s", long_id)
            if long_id.startswith(short_id):
                return long_id
        msg = "Failed to translate short id (%s) into long id!"
        raise Exception, msg % short_id

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

        Raises :py:exc:`exceptions.ValueError` when a string with an
        incorrect format is given.

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
    def key(self):
        """
        Get a tuple with the image's repository and tag.
        """
        return (self.repository, self.tag)

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

    """
    Dumb object to hold session variables associated with a running Docker
    container.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        """
        Reset all known session variables to ``None``.
        """
        self.container_id = None
        self.custom_image = None
        self.remote_terminal = None
        self.ssh_endpoint = None

class SecureShellTimeout(Exception):
    """
    Raised by :py:attr:`Container.ssh_endpoint` when Redock fails to connect to
    the Docker container within a reasonable amount of time (10 seconds by
    default).
    """

class NoContainerRunning(Exception):
    """
    Raised by :py:func:`Container.check_active` when a :py:class:`Container`
    doesn't have an associated Docker container running.
    """

# vim: ts=4 sw=4 et
