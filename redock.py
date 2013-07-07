# Human friendly wrapper around Docker.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 7, 2013
# URL: https://github.com/xolox/python-redock
#
# External references:
#  - https://github.com/dotcloud/docker-py
#  - https://github.com/dotcloud/docker/issues/313#issuecomment-16003232

# Standard library modules.
import getopt
import logging
import os
import pipes
import re
import socket
import subprocess
import sys
import textwrap
import time

# External dependencies.
import coloredlogs
import docker
import humanfriendly
import netifaces
import update_dotdee
import verboselogs

# Initialize the logger.
logger = verboselogs.VerboseLogger('redock')
logger.setLevel(logging.INFO)
logger.addHandler(coloredlogs.ColoredStreamHandler())

# The default base image for new containers.
DEFAULT_BASE_IMAGE = 'ubuntu:precise'

# The timeout while waiting for a container to become reachable over SSH.
SSH_GRACE_PERIOD = 60

# Directory with generated SSH key pairs on the host.
SSH_KEY_CATALOG = os.path.expanduser('~/.redock/ssh')

def main():
    """
    Command line interface for the ``redock`` program.
    """
    # Parse and validate the command line arguments.
    try:
        # Command line option defaults.
        base = DEFAULT_BASE_IMAGE
        hostname = None
        message = None
        # Parse the command line options.
        options, arguments = getopt.getopt(sys.argv[1:], 'b:n:m:vh',
                                          ['base=', 'hostname=', 'message=', 'verbose', 'help'])
        for option, value in options:
            if option in ('-b', '--base'):
                base = value
            elif option in ('-n', '--hostname'):
                hostname = value
            elif option in ('-m', '--message'):
                message = value
            elif option in ('-v', '--verbose'):
                if logger.getEffectiveLevel() == logging.INFO:
                    logger.setLevel(logging.VERBOSE)
                elif logger.getEffectiveLevel() == logging.VERBOSE:
                    logger.setLevel(logging.DEBUG)
            elif option in ('-h', '--help'):
                print_usage()
                return
            else:
                # Programming error...
                assert False, "Unhandled option!"
        # Handle the positional arguments.
        if len(arguments) < 2:
            print_usage()
            return
        supported_actions = ('start', 'stop', 'save')
        action = arguments.pop(0)
        if action not in supported_actions:
            msg = "Action not supported: %r (supported actions are: %s)"
            raise Exception, msg % (action, ', '.join(supported_actions))
    except Exception, e:
        logger.error("Failed to parse command line arguments!")
        logger.exception(e)
        print_usage()
        sys.exit(1)
    # Start the container and connect to it over SSH.
    try:
        for image_name in arguments:
            container = Container(image=Image.coerce(image_name),
                                  base=Image.coerce(base),
                                  hostname=hostname)
            if action == 'start':
                container.initialize()
                if len(arguments) == 1 and all(os.isatty(n) for n in range(3)):
                    logger.info("Detected interactive terminal, connecting to container ..")
                    subprocess.Popen(['ssh', container.ssh_alias]).wait()
                container.detach()
            elif action == 'stop':
                container.stop()
            elif action == 'save':
                container.commit_changes(message=message)
            else:
                # Programming error...
                assert False, "Unhandled action!"
    except Exception, e:
        logger.exception(e)
        sys.exit(1)

def print_usage():
    """
    Print a usage message to the console.
    """
    usage = textwrap.dedent("""
        Usage: redock [OPTIONS] ACTION CONTAINER..

        Create and manage Docker containers and images. Supported actions are
        `start', `ssh' and `stop'.

        Supported options:

          -b, --base=IMAGE     override the base image (defaults to {base})
          -n, --hostname=NAME  set container host name (defaults to image tag)
          -m, --message=TEXT   message for image created with `save' action
          -v, --verbose        make more noise (can be repeated)
          -h, --help           show this message and exit
    """).strip()
    print usage.format(base=DEFAULT_BASE_IMAGE)

class Container(object):

    """
    Simple representation of Docker containers.
    """

    def __init__(self, image, base=DEFAULT_BASE_IMAGE, hostname=None):
        """
        Initialize a :py:class:`Container` instance from the given arguments.

        :param image: The repository and tag of the container's image (in the
                      format expected by :py:class:`Image.coerce()`).
        :param base: The repository and tag of the base image for the container
                     (in the format expected by :py:class:`Image.coerce()`).
        """
        self.logger = logger
        self.image = Image.coerce(image)
        self.base = Image.coerce(base)
        self.hostname = hostname or self.image.tag
        self.container_id = None
        self.custom_image = None
        self.remote_terminal = None

    def initialize(self):
        """
        Connect to Docker, create the container if it doesn't exist yet,
        install and configure an SSH server in the container and wait for the
        container to become reachable over SSH.
        """
        self.initialize_client()
        self.initialize_container()

    def stop(self):
        """
        Stop and remove the container. All changes  since the last time that
        :py:func:`Container.commit_changes()` was called will be lost.
        """
        self.initialize_client()
        if self.find_running_container():
            self.logger.info("Killing container ..")
            self.docker.kill(self.container_id)
            self.logger.info("Removing container ..")
            self.docker.remove_container(self.container_id)

    def initialize_client(self):
        """
        Initialize the Docker client and connect to the Docker API server.
        """
        if not hasattr(self, 'docker'):
            try:
                self.logger.debug("Connecting to Docker daemon ..")
                self.docker = docker.Client()
                self.logger.debug("Successfully connected to Docker.")
            except Exception, e:
                self.logger.error("Failed to connect to Docker!")
                self.logger.exception(e)
                raise

    def initialize_container(self):
        """
        Initialize the Docker container:
        
        1. Download the base image (only when needed).
        2. Install and configure an SSH server (only when needed).
        3. Start the SSH server.
        4. Wait for the container to become reachable over SSH.
        """
        if not self.find_running_container():
            if not self.find_custom_image():
                self.logger.info("Image %r doesn't exist yet, creating it ..", self.image)
                self.download_base_image()
                self.initialize_base_image()
            else:
                self.start_ssh_server()
            self.configure_ssh_access()

    def attach(self):
        """
        Attach to the container so the user knows what they are waiting for.
        """
        self.check_container_active()
        if not self.remote_terminal:
            command = ['docker', 'attach', self.container_id]
            self.logger.verbose("Attaching to container's terminal using command: %s", quote_command_line(command))
            self.remote_terminal = subprocess.Popen(command, stdin=open(os.devnull), stdout=sys.stderr)

    def detach(self):
        """
        Detach from the container.
        """
        if self.remote_terminal:
            if self.remote_terminal.poll() is None:
                self.remote_terminal.kill()
            self.remote_terminal = None

    def find_running_container(self):
        """
        Check to see if the current container is already running.
        """
        self.logger.info("Looking for running container ..")
        for container in self.docker.containers():
            if container.get('Image') == self.image.name:
                self.container_id = container['Id']
                self.logger.info("Found running container: %s", self.container_id)
                return True

    def find_custom_image(self):
        """
        Look for an existing image belonging to the container.

        :returns: A :py:class:`Image` instance if an existing image was found,
                  ``None`` otherwise.
        """
        if not self.custom_image:
            self.logger.debug("Looking for existing image: %r", self.image)
            self.custom_image = self.find_named_image(self.image)
            if self.custom_image:
                self.logger.debug("Found existing image: %r", self.custom_image)
            else:
                self.logger.debug("No existing image found.")
        return self.custom_image

    def download_base_image(self):
        """
        Download the base image required to create the container.
        """
        self.logger.verbose("Looking for existing base image of %s ..", self.image)
        if not self.find_named_image(self.base):
            download_timer = humanfriendly.Timer()
            self.logger.info("Downloading base image: %s", self.base)
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
            if image.get('Repository') == image_to_find.repository and image.get('Tag') == image_to_find.tag:
                matches.append(image)
        if matches:
            matches.sort(key=lambda i: i['Created'])
            image = matches[-1]
            return Image(repository=image['Repository'],
                         tag=image['Tag'],
                         id=image['Id'][:12])

    def initialize_base_image(self):
        """
        Initialize a custom image from a base image by installing an SSH server
        and a generated SSH public key.
        """
        self.install_ssh_server()
        self.start_ssh_server()

    def install_ssh_server(self):
        """
        Install and configure an SSH server inside a container.
        """
        install_timer = humanfriendly.Timer()
        self.logger.info("Installing SSH server inside container (please be patient) ..")
        template = '{install} && mkdir -p /root/.ssh && echo {key} > /root/.ssh/authorized_keys'
        command_line = template.format(install=apt_get_install('openssh-server'),
                                       key=pipes.quote(self.get_ssh_public_key()))
        self.fork_command_through_docker(command_line)
        self.docker.wait(self.container_id)
        self.commit_changes(message="Installed SSH server & public key")
        self.logger.info("Installed SSH server in %s.", install_timer)

    def start_ssh_server(self):
        """
        We have to start the SSH server ourselves because Docker replaces
        ``/sbin/init`` inside the container, which means ``sshd`` is not
        managed by upstart. Also Docker works on the principle of running some
        main application in the foreground; in our case it will be ``sshd``.
        """
        self.logger.info("Starting SSH server ..")
        command_line = 'mkdir -p -m0755 /var/run/sshd && /usr/sbin/sshd -eD'
        self.fork_command_through_docker(command_line)

    def get_ssh_client_command(self, ip_address=None, port_number=None):
        """
        Generate an SSH client command line that connects to the container.

        :param binary: ``True`` if the SSH client command line should include
                       ``-e none``, ``False`` otherwise.
        :param include_ip: 
        """
        command = ['ssh']
        # Connect as the root user inside the container.
        command.extend(['-l', 'root'])
        # Connect using the generated SSH private key.
        command.extend(['-i', self.get_ssh_private_key()])
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

    def configure_ssh_access(self):
        """
        Update ~/.ssh/config so the container can be started by connecting to
        it over SSH.
        """
        self.logger.verbose("Configuring SSH access ..")
        filename = os.path.expanduser('~/.ssh/config')
        directory = "%s.d" % filename
        config = update_dotdee.UpdateDotDee(filename)
        with open(os.path.join(directory, 'redock:%s' % self.image.name), 'w') as handle:
            ip_address, port_number = self.ssh_endpoint
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
                       key=self.get_ssh_private_key(),
                       redock=pipes.quote(os.path.abspath(sys.argv[0])),
                       container=pipes.quote(self.image.name))))
        config.update_file()
        self.logger.info("Successfully configured SSH access. Use this command: ssh %s", self.ssh_alias)

    @property
    def ssh_endpoint(self):
        """
        Wait for the container to become reachable over SSH and return the (IP
        address, port number) that can be used to connect to the container over
        SSH.
        """
        self.check_container_active()
        if hasattr(self, 'cached_ssh_endpoint'):
            return self.cached_ssh_endpoint
        # Get the local port connected to the container.
        host_port = int(self.docker.port(self.container_id, '22'))
        self.logger.debug("Configured port redirection for container %s: %s:%i -> %s:%i",
                          self.container_id, socket.gethostname(), host_port, self.hostname, 22)
        # Give the container time to finish the SSH server installation.
        self.logger.verbose("Waiting for SSH connection to %s (max %i seconds) ..", self.container_id, SSH_GRACE_PERIOD)
        global_timeout = time.time() + SSH_GRACE_PERIOD
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
                    self.cached_ssh_endpoint = (ip_address, host_port)
                    self.logger.debug("Connected to %s at %s using SSH in %s.", self.image.name, self.ssh_endpoint, ssh_timer)
                    return self.cached_ssh_endpoint
            time.sleep(1)
        msg = "Time ran out while waiting to connect to container %s over SSH! (Most likely something went wrong while initializing the container..)"
        raise Exception, msg % self.image.name

    def wait_for_docker_command(self, command):
        """
        Create the container, start it, run the given command and wait for the
        command to finish.

        :param command: The Bash command line to execute inside the container
                        (a string).
        """
        self.fork_command_through_docker(command)
        self.docker.wait(self.container_id)

    def fork_command_through_docker(self, command):
        """
        Create and start the container, fork the given command inside the
        container and return control to the caller without waiting for the
        command inside the container to finish.

        :param command: The Bash command line to execute inside the container
                        (a string).
        """
        # Find the image to use as a base for the container.
        image = self.find_custom_image() or self.find_named_image(self.base)
        self.logger.debug("Creating container from image: %r", image)
        # Start the container with the given command.
        result = self.docker.create_container(image=image.unique_name,
                                              command='bash -c %s' % pipes.quote(command),
                                              hostname=self.hostname,
                                              ports=['22'])
        # Remember and report the container id.
        self.container_id = result['Id']
        self.logger.debug("Created container: %s", self.container_id)
        # Start the command inside the container.
        self.logger.debug("Running command: %s", command)
        self.docker.start(self.container_id)
        # Make sure the user sees all output from the container.
        self.attach()

    def commit_changes(self, message=None, author=None):
        """
        Commit any changes to the container.
        """
        self.initialize_client()
        self.check_container_active()
        self.logger.verbose("Committing changes: %s", message or 'no description given')
        self.docker.commit(self.container_id, repository=self.image.repository,
                           tag=self.image.tag, message=message, author=author)
        self.stop()
        self.initialize()

    def __repr__(self):
        """
        Pretty print a :py:class:`Container` object.
        """
        template = "Container(image=%r, base=%r, hostname=%r)"
        return template % (self.image, self.base, self.hostname)

    def get_ssh_private_key(self):
        """
        Get the SSH private key associated with the container.
        """
        return os.path.join(SSH_KEY_CATALOG, self.image.name)

    def get_ssh_public_key(self):
        """
        Get the SSH public key associated with the container.
        """
        public_key_file = os.path.join(SSH_KEY_CATALOG, '%s.pub' % self.image.name)
        if not os.path.isfile(public_key_file):
            self.generate_ssh_key_pair()
        with open(public_key_file) as handle:
            return handle.read().strip()

    def generate_ssh_key_pair(self):
        """
        Generate an SSH key pair for communication between the host system and
        the Docker container.
        """
        self.logger.verbose("Checking if we need to generate a new SSH key pair ..")
        self.create_directory(SSH_KEY_CATALOG)
        private_key_file = self.get_ssh_private_key()
        if os.path.isfile(private_key_file):
            self.logger.verbose("SSH key pair was previously generated: %s", private_key_file)
        else:
            self.logger.info("No existing SSH key pair found, generating new pair: %s", private_key_file)
            command = ['ssh-keygen', '-t', 'rsa', '-f', private_key_file, '-N', '', '-C', 'root@%s' % self.hostname]
            ssh_keygen = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = ssh_keygen.communicate(input='')
            if ssh_keygen.returncode != 0:
                msg = "Failed to generate SSH key pair! (command exited with nonzero exit code %d: %r)"
                raise Exception, msg % (ssh_keygen.returncode, command)

    # Miscellaneous methods.

    def check_container_active(self):
        """
        Make sure a container is active.
        """
        if not (self.container_id or self.find_running_container()):
            raise Exception, "No active container!"

    def create_directory(self, directory):
        """
        Create a directory if it doesn't exist yet.
        """
        if not os.path.isdir(directory):
            os.makedirs(directory)

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
        Coerce the value given as the first argument to an :py:class:`Image`.

        :param value: The name of the image, expected to be a string containing
                      the image's repository and tag, separated by a colon.
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
        Get the human readable name of an :py:class:`Image` as a string in the
        format ``repository:tag``.
        """
        return "%s:%s" % (self.repository, self.tag)

    @property
    def unique_name(self):
        """
        Get the machine readable unique name of an :py:class:`Image`.
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
            properties.append("id=%r" % self.id)
        return "Image(%s)" % ", ".join(properties)

def find_local_ip_addresses():
    """
    To connect to a running Docker container over SSH (TCP) we need to connect
    to a specific port number on an IP address associated with a local network
    interface:

        Please note that because of how routing works
        connecting to localhost or 127.0.0.1 won't work.

    See also: http://docs.docker.io/en/latest/use/basics/

    :returns: A :py:class:`set` of IP addresses associated with local network
              interfaces.
    """
    ip_addresses = set()
    for name in sorted(netifaces.interfaces(), key=str.lower):
        for addresses in netifaces.ifaddresses(name).values():
            for properties in addresses:
                address = properties.get('addr')
                # As mentioned above we're specifically *not* interested in loop back interfaces.
                if address.startswith('127.'):
                    continue
                # I'm not interested in IPv6 addresses right now.
                if ':' in address:
                    continue
                if address:
                    ip_addresses.add(address)
    return ip_addresses

def apt_get_install(*packages):
    """
    Generate a command to install the given packages with ``apt-get``.

    :param packages: The names of the package(s) to be installed.
    :returns: The ``ap-get`` command line as a single string.
    """
    command = ['DEBIAN_FRONTEND=noninteractive',
               'apt-get', 'install', '-q', '-y',
               '--no-install-recommends']
    return quote_command_line(command + list(packages))

def quote_command_line(command):
    """
    Quote the tokens in a shell command line.

    :param command: A list with the command name and arguments.
    :returns: The command line as a single string.
    """
    return ' '.join(pipes.quote(s) for s in command)

def slug(text):
    """
    Convert text to a "slug".

    :param text: The original text, e.g. "Some Random Text!".
    :returns: The slug text, e.g. "some-random-text".
    """
    slug = re.sub('[^a-z0-9]+', '-', text.lower())
    return slug.strip('-')

# vim: ts=4 sw=4 et
