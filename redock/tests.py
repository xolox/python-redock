# Tests for Redock.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: August 6, 2013
# URL: https://github.com/xolox/python-redock

# Standard library modules.
import logging
import pipes
import subprocess
import unittest

# External dependencies.
import coloredlogs

# Modules included in our package.
from redock.api import Container, Image
from redock.logger import root_logger

class RedockTestCase(unittest.TestCase):

    def setUp(self):
        coloredlogs.install()
        root_logger.setLevel(logging.DEBUG)

    def test_image_coercion(self):
        image = Image.coerce('redock:test')
        self.assertEqual(image.repository, 'redock')
        self.assertEqual(image.tag, 'test')
        self.assertEqual(image.key, ('redock', 'test'))
        self.assertEqual(image.name, 'redock:test')
        self.assertEqual(image.unique_name, 'redock:test')

    def test_start_container(self):
        hostname = 'whatever'
        # Start a test container.
        container = Container('redock:test', hostname=hostname)
        container.start()
        try:
            # Try to connect to the container over SSH.
            ssh_client = subprocess.Popen(['ssh', container.ssh_alias, 'hostname'],
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE)
            stdout, stderr = ssh_client.communicate()
            # Check the results.
            self.assertEqual(ssh_client.returncode, 0)
            self.assertEqual(stdout.strip(), hostname)
        finally:
            # Kill the container.
            container.kill()
        # Verify that the container is no longer reachable over SSH.
        ssh_client = subprocess.Popen(['ssh', '-q', container.ssh_alias, 'hostname'],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE)
        stdout, stderr = ssh_client.communicate()
        self.assertNotEqual(ssh_client.returncode, 0)

    def test_commit_and_delete_container(self):
        pathname = '/root/peter-was-here'
        # Start a test container.
        container = Container('redock:test')
        container.start()
        try:
            # Create a file on the container's file system.
            ssh_client = subprocess.Popen(['ssh', container.ssh_alias, 'touch %s' % pipes.quote(pathname)])
            self.assertEqual(ssh_client.wait(), 0)
            # Commit the container's file system to an image.
            container.commit()
            # Restart the container.
            container.kill()
            container.start()
            # Make sure the file still exists.
            ssh_client = subprocess.Popen(['ssh', container.ssh_alias, 'test -f %s' % pipes.quote(pathname)])
            self.assertEqual(ssh_client.wait(), 0)
        finally:
            # Kill the container.
            container.kill()
            # Delete the image.
            container.delete()

if __name__ == '__main__':
    unittest.main()

# vim: ts=4 sw=4 et
