#!/usr/bin/env python

# Setup script for redock.
#
# Author: Peter Odding <peter@peterodding.com>
# Last Change: July 16, 2013
# URL: https://github.com/xolox/python-redock

import re
from os.path import abspath, dirname, join
from setuptools import setup, find_packages

# Find the directory containing the source distribution.
source_directory = dirname(abspath(__file__))

# Find the current version.
module = join(source_directory, 'redock', '__init__.py')
for line in open(module, 'r'):
    match = re.match(r'^__version__\s*=\s*["\']([^"\']+)["\']$', line)
    if match:
        version_string = match.group(1)
        break
else:
    raise Exception, "Failed to extract version from redock/__init__.py!"

# Fill in the long description (for the benefit of PyPi)
# with the contents of README.rst (rendered by GitHub).
readme_text = open(join(source_directory, 'README.rst'), 'r').read()

# Fill in the "install_requires" field based on requirements.txt.
requirements = [l.strip() for l in open(join(source_directory, 'requirements.txt'), 'r')]

setup(name='redock',
      version=version_string,
      description="Human friendly wrapper around Docker",
      long_description=readme_text,
      url='https://github.com/xolox/python-redock',
      author='Peter Odding',
      author_email='peter@peterodding.com',
      packages=find_packages(),
      entry_points=dict(console_scripts=['redock = redock.cli:main']),
      install_requires=requirements,
      test_suite='redock.tests')
