Documentation for redock
========================

Welcome to the documentation for Redock |release|. Redock is a human friendly
wrapper around Docker_, the `Linux container engine`_. Docker implements a
lightweight form of virtualization_ that makes it possible to start and stop
virtual machines in less than a second. Redock comes in two parts:

1. The command line program ``redock`` whose main goal to to be simple to use.

2. A Python API for more advanced use cases (for example the command line
   program is built on top of the API).

The documentation also consists of two parts: The main text with installation
and usage instructions and the API documentation.

Introduction & usage
--------------------

The first part of the documentation is the readme which is targeted at users of
the ``redock`` command line program. Here are the topics discussed in the
readme:

.. toctree::
   :maxdepth: 2

   users.rst

API documentation
-----------------

The second part of the documentation is targeted at developers who wish to use
Redock in their own programs. Here are the contents of the API documentation:

.. toctree::
   :maxdepth: 2

   developers.rst

.. External references:
.. _Docker: http://www.docker.io/
.. _Linux container engine: http://en.wikipedia.org/wiki/LXC
.. _virtualization: http://en.wikipedia.org/wiki/Virtualization
