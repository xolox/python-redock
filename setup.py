#!/usr/bin/env python

from os.path import abspath, dirname, join
from setuptools import setup, find_packages

# Find the directory containing the source distribution.
directory = dirname(abspath(__file__))

# Fill in the long description (for the benefit of PyPi)
# with the contents of README.rst (rendered by GitHub).
readme_text = open(join(directory, 'README.rst'), 'r').read()

# Fill in the "install_requires" field based on requirements.txt.
requirements = [l.strip() for l in open(join(directory, 'requirements.txt'), 'r')]

setup(name='redock',
      version='0.3',
      description="Human friendly wrapper around Docker",
      long_description=readme_text,
      url='https://github.com/xolox/python-redock',
      author='Peter Odding',
      author_email='peter@peterodding.com',
      packages=find_packages(),
      entry_points=dict(console_scripts=['redock = redock.cli:main']),
      install_requires=requirements)
