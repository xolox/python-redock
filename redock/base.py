# Initialization of the base image used by Redock.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 15, 2013
# URL: https://github.com/xolox/python-redock

"""
The :py:mod:`redock.base` module implements the initialization of the base
image used by Redock. You'll probably never need to use this module directly
because :py:func:`redock.api.Container.start()` calls
:py:func:`find_base_image()` and :py:func:`create_base_image()` as needed.
"""

# Standard library modules.
import pipes

# External dependencies.
from humanfriendly import Timer

# Modules included in our package.
from redock.logger import get_logger
from redock.utils import (RemoteTerminal, get_ssh_public_key,
                          select_ubuntu_mirror, summarize_id)

# The logger for this module.
logger = get_logger(__name__)

# The repository and tag of Redock's base image.
BASE_IMAGE_REPO = 'redock'
BASE_IMAGE_TAG = 'base'
BASE_IMAGE_NAME = '%s:%s' % (BASE_IMAGE_REPO, BASE_IMAGE_TAG)
SSHD_LOG_FILE = '/var/log/sshd.log'

APT_CONFIG = '''
# /etc/apt/apt.conf.d/90redock:
# Disable automatic installation of recommended packages. Debian doesn't do
# this; the policy change came from Ubuntu, and I don't like it one bit!
# Fortunately we can still change it :-)

APT::Install-Recommends "false";

# vim: ft=perl
'''

SOURCES_LIST = '''
# /etc/apt/sources.list: Use a local package mirror.

deb {mirror} precise main universe

# vim: ft=debsources
'''

SUPERVISOR_CONFIG = '''
# /etc/supervisor/conf.d/ssh-server.conf:
# Replacement for /etc/init/ssh.conf that doesn't need upstart.

[program:ssh-server]
command = bash -c 'mkdir -p -m0755 /var/run/sshd && /usr/sbin/sshd -eD'
# stdout_logfile = /var/log/supervisor/ssh-server.log
# redirect_stderr = true
autorestart = true

# vim: ft=dosini
'''.format(log_file=SSHD_LOG_FILE)

def find_base_image(client):
    """
    Find the id of the base image that's used by Redock to create new
    containers. If the image doesn't exist yet it will be created using
    :py:func:`create_base_image()`.

    :param client: Connection to Docker (instance of :py:class:`docker.Client`)
    :returns: The unique id of the base image.
    """
    logger.verbose("Looking for base image ..")
    image_id = find_named_image(client, BASE_IMAGE_REPO, BASE_IMAGE_TAG)
    if image_id:
        logger.verbose("Found base image: %s", summarize_id(image_id))
        return image_id
    else:
        logger.verbose("No base image found, creating it ..")
        return create_base_image(client)

def create_base_image(client):
    """
    Create the base image that's used by Redock to create new containers. This
    base image differs from the ubuntu:precise_ image (on which it is based) on
    a couple of points:

    - Automatic installation of recommended packages is disabled to conserve
      disk space.

    - The Ubuntu package mirror is set to a geographically close location to
      speed up downloading of system packages (see
      :py:func:`redock.utils.select_ubuntu_mirror()`).

    - The package list is updated to make sure apt-get_ installs the most up to
      date packages.

    - The following system packages are installed:

      language-pack-en-base_
        In a base Docker Ubuntu 12.04 image lots of commands complain loudly
        about the locale_. This silences the warnings by fixing the problem
        (if you want to call it that).

      openssh-server_
        After creating a new container Redock will connect to it over SSH_,
        so having an SSH server installed is a good start :-)

      supervisor_
        The base Docker Ubuntu 12.04 image has init_ (upstart_) disabled.
        Indeed we don't need all of the bagage that comes with init but it is
        nice to have a process runner for the SSH_ server (and eventually maybe
        more).

    - The initscripts_ and upstart_ system packages are marked 'on hold' so
      that apt-get_ will not upgrade them. This makes it possible to run
      ``apt-get dist-upgrade`` inside containers.

    - An SSH_ key pair is generated and the SSH public key is installed inside
      the base image so that Redock can connect to the container over SSH (you
      need ssh-keygen_ installed).

    - Supervisor_ is configured to automatically start the SSH_ server.

    :param client: Connection to Docker (instance of :py:class:`docker.Client`)
    :returns: The unique id of the base image.

    .. _apt-get: http://manpages.ubuntu.com/manpages/precise/man8/apt-get.8.html
    .. _init: http://manpages.ubuntu.com/manpages/precise/man8/init.8.html
    .. _initscripts: http://packages.ubuntu.com/precise/initscripts
    .. _language-pack-en-base: http://packages.ubuntu.com/precise/language-pack-en-base
    .. _locale: http://en.wikipedia.org/wiki/Locale
    .. _openssh-server: http://packages.ubuntu.com/precise/openssh-server
    .. _ssh-keygen: http://manpages.ubuntu.com/manpages/precise/man1/ssh-keygen.1.html
    .. _supervisor: http://packages.ubuntu.com/precise/supervisor
    .. _ubuntu:precise: https://index.docker.io/_/ubuntu/
    .. _upstart: http://packages.ubuntu.com/precise/upstart
    """
    download_image(client, 'ubuntu', 'precise')
    creation_timer = Timer()
    logger.info("Initializing base image (this can take a few minutes but you only have to do it once) ..")
    command = ' && '.join([
        'echo %s > /etc/apt/apt.conf.d/90redock' % pipes.quote(APT_CONFIG.strip()),
        'echo %s > /etc/apt/sources.list' % pipes.quote(SOURCES_LIST.format(mirror=select_ubuntu_mirror()).strip()),
        'apt-get update',
        'DEBIAN_FRONTEND=noninteractive apt-get install -q -y language-pack-en-base openssh-server supervisor',
        'apt-get clean', # Don't keep the +/- 20 MB of *.deb archives after installation.
        # Make it possible to run `apt-get dist-upgrade'.
        # https://help.ubuntu.com/community/PinningHowto#Introduction_to_Holding_Packages
        'apt-mark hold initscripts upstart',
        # Install the generated SSH public key.
        'mkdir -p /root/.ssh',
        'echo %s > /root/.ssh/authorized_keys' % pipes.quote(get_ssh_public_key()),
        # Create the Supervisor configuration for the SSH server.
        'echo %s > /etc/supervisor/conf.d/ssh-server.conf' % pipes.quote(SUPERVISOR_CONFIG.strip())])
    logger.debug("Generated command line: %s", command)
    result = client.create_container(image='ubuntu:precise',
                                     command='bash -c %s' % pipes.quote(command),
                                     hostname='redock-template',
                                     ports=['22'])
    container_id = result['Id']
    for text in result.get('Warnings', []):
      logger.warn("%s", text)
    logger.verbose("Created container %s.", summarize_id(container_id))
    client.start(container_id)
    with RemoteTerminal(container_id):
        logger.info("Waiting for initialization to finish ..")
        client.wait(container_id)
        logger.info("Finished initialization in %s.", creation_timer)
    commit_timer = Timer()
    logger.info("Saving initialized container as new base image ..")
    result = client.commit(container_id, repository='redock', tag='base')
    logger.info("Done! Committed base image as %s in %s.", summarize_id(result['Id']), commit_timer)
    return result['Id']

def find_named_image(client, repository, tag):
    """
    Find the most recent Docker image with the given repository and tag.

    :param repository: The name of the image's repository.
    :param tag: The name of the image's tag.
    :returns: The unique id of the most recent image available, or ``None`` if
              no images were matched.
    """
    matches = []
    for image in client.images():
        if image.get('Repository') == repository and image.get('Tag') == tag:
            matches.append(image)
    if matches:
        matches.sort(key=lambda i: i['Created'])
        return matches[-1]['Id']

def download_image(client, repository, tag):
    """
    Download the requested image. If the image is already available locally it
    won't be downloaded again.

    :param client: Connection to Docker (instance of :py:class:`docker.Client`)
    :param repository: The name of the image's repository.
    :param tag: The name of the image's tag.
    """
    if not find_named_image(client, repository, tag):
        download_timer = Timer()
        logger.info("Downloading image %s:%s (please be patient, this can take a while) ..", repository, tag)
        client.pull(repository=repository, tag=tag)
        logger.info("Finished downloading image in %s.", download_timer)

# vim: ts=4 sw=4 et
