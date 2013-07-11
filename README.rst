redock: A human friendly wrapper around Docker
==============================================

Redock is a human friendly wrapper around Docker_, the `Linux container
engine`_. Docker implements a lightweight form of virtualization_ that makes it
possible to start and stop virtual machines in less than a second. Before
Docker the use of virtualization meant conventional virtual machines with all
of the associated bloat. Docker makes it ridiculously cheap and fast to
start/save/kill containers. This opens up exciting new possibilities for
DevOps:

- Complex build environments can be split up into isolated containers where
  each container is concerned with the build requirements of a single project.
  If a project's build goes out of hand you just trash the container and go on
  your merry way :-)

- The correctness of automated deployment systems (and distributed systems in
  general) can be verified by using containers to host the configuration
  management server and agents.

- To be honest, Docker is so fast that I could imagine myself building a test
  suite of a complete cluster on top of it.

The last point is the reason why I started working on Redock. In my initial
experiments with Docker_ I found a lot of sharp edges (both in the lack of
documentation and in the implementation of Docker_ and its Python API) but at
the same time my fingers were itching to wrap Docker in an easy to use and
human friendly wrapper to try and unleash its potential.

What Redock gives you is Docker without all the hassle: When you create a
container, Redock will install, configure and start an SSH_ server and open
an interactive SSH session to the container. What you do with the container
after that is up to you...

Usage
-----

You will need to have Docker_ installed before you can use Redock, please refer
to Docker's `installation instructions`_. After you've installed Docker you can
install Redock using the following command::

    $ pip install redock

Once you've installed the program, here's how you create a container::

    $ redock start test

If you run this command interactively and you start a single container, Redock
will start an interactive SSH_ session that connects you to the container. In
any case you will now be able to connect to the container over SSH_ using the
name you gave to the container suffixed with ``-container``::

    $ ssh test-container

This works because your ``~/.ssh/config`` has been updated to include a host
definition for the container. This means you can connect using rsync_ or
anything else which works on top of SSH_ (e.g. to bootstrap a configuration
management system). When you're done playing around with the container you can
save your changes with the following command::

    $ redock commit test

This command will persist the state of the container's file system in a Docker
image. The next time you run Redock with the same name it will create a
container based on the existing disk image. To kill and delete a running
container you use the following command::

    $ redock kill test

This will discard all changes made to the file system inside the container
since the last time that ``redock commit`` was used.

Contact
-------

The latest version of Redock is available on PyPI_ and GitHub_. For bug reports
please create an issue on GitHub_. If you have questions, suggestions, etc.
feel free to send me an e-mail at `peter@peterodding.com`_.

License
-------

This software is licensed under the `MIT license`_.

© 2013 Peter Odding.

.. External references:
.. _Docker: http://www.docker.io/
.. _GitHub: https://github.com/xolox/python-redock
.. _installation instructions: http://www.docker.io/gettingstarted/
.. _Linux container engine: http://en.wikipedia.org/wiki/LXC
.. _MIT license: http://en.wikipedia.org/wiki/MIT_License
.. _peter@peterodding.com: peter@peterodding.com
.. _PyPI: https://pypi.python.org/pypi/redock
.. _rsync: http://en.wikipedia.org/wiki/Rsync
.. _SSH: http://en.wikipedia.org/wiki/Secure_Shell
.. _virtualization: http://en.wikipedia.org/wiki/Virtualization
