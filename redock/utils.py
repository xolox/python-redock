# Utility functions for the `redock' program.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 8, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import pipes
import re

# External dependencies.
import netifaces

def find_local_ip_addresses():
    """
    To connect to a running Docker container over SSH (TCP) we need to connect
    to a specific port number on an IP address associated with a local network
    interface on the host system:

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

def summarize_id(id):
    """
    Docker uses hexadecimal strings of 65 characters to uniquely identify
    containers, images and other objects. Docker's API always reports
    full IDs of 65 characters, but the ``docker`` program abbreviates
    these IDs to 12 characters in the user interface. We do the same
    because it makes the output a lot user friendlier.

    :param id: A hexadecimal ID of 65 characters.
    :returns: A summarized ID of 12 characters.
    """
    return id[:12]

def slug(text):
    """
    Convert text to a "slug".

    :param text: The original text, e.g. "Some Random Text!".
    :returns: The slug text, e.g. "some-random-text".
    """
    slug = re.sub('[^a-z0-9]+', '-', text.lower())
    return slug.strip('-')

# vim: ts=4 sw=4 et
