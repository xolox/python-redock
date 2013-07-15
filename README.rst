redock: A human friendly wrapper around Docker
==============================================

Redock is a human friendly wrapper around Docker_, the `Linux container
engine`_. Docker implements a lightweight form of virtualization_ that makes it
possible to start and stop "virtual machines" in less than a second. Before
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

Status
------

Redock should be considered alpha quality software. So far it has been used by
a single person (me). Right now it's intended for development work, not
production use. This might change over time, depending on my experiences with
Docker over the coming weeks / months (I'm specifically concerned with
stability and performance).

By the way the same can and should be said about Docker_ (its site says as
much). During heavy testing of Redock I've experienced a number of unhandled
kernel mode NULL pointer dereferences that didn't crash the host system but
certainly also didn't inspire confidence ;-). It should be noted that these
issues didn't occur during regular usage; only heavy testing involving the
creation and destruction of dozens of Docker containers would trigger the
issue.

There's one thing I should probably mention here as a disclaimer: Redock
rewrites your SSH configuration (``~/.ssh/config``) using update-dotdee_. I've
tested this a fair bit, but it's always a good idea to keep backups (hint).

Usage
-----

You will need to have Docker_ installed before you can use Redock, please refer
to Docker's `installation instructions`_. After you've installed Docker you can
install Redock using the following command::

    $ pip install redock

This downloads and installs Redock using pip_ (the Python package manager).
Redock is written in Python so you need to have Python installed. Redock pulls
in a bunch of dependencies_ so if you're familiar with `virtual environments`_
you might want to use one :-). Once you've installed Docker and Redock, here's
how you create a container::

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
since the last time that ``redock commit`` was used. The Docker image
associated with a container can be deleted like this::

    $ redock delete test

Naming conventions
~~~~~~~~~~~~~~~~~~

In the examples above the name ``test`` is used. This name is used by Redock to
identify the running container (created with ``redock start``) and any
associated images (created with ``redock commit``). By using multiple names you
can run multiple containers in parallel and you can suspend / resume "long
term" containers.

The names accepted by Redock are expected to be of the form ``repository:tag``
(two words separated by a colon):

1. The first part (``repository`` in the example) is a top level name space for
   Docker images. For example there is a repository called ``ubuntu`` that
   contains the official base images. Similarly Redock uses the repository
   ``redock`` for the base image it creates on the first run.

2. The second part (``tag`` in the example) is the name of a specific container
   and/or image; I usually just sets it to the host name of the system that
   will be running inside the container.

If the colon is missing the ``repository`` will be set to your username (based
on the environment variable ``$USER``).

Contact
-------

The latest version of Redock is available on PyPI_ and GitHub_. The API
documentation is `hosted on Read The Docs`_. For bug reports please create an
issue on GitHub_. If you have questions, suggestions, etc. feel free to send me
an e-mail at `peter@peterodding.com`_.

License
-------

This software is licensed under the `MIT license`_.

© 2013 Peter Odding.

.. External references:
.. _dependencies: https://github.com/xolox/python-redock/blob/master/requirements.txt
.. _Docker: http://www.docker.io/
.. _GitHub: https://github.com/xolox/python-redock
.. _hosted on Read The Docs: https://redock.readthedocs.org/en/latest/
.. _installation instructions: http://www.docker.io/gettingstarted/
.. _Linux container engine: http://en.wikipedia.org/wiki/LXC
.. _MIT license: http://en.wikipedia.org/wiki/MIT_License
.. _peter@peterodding.com: peter@peterodding.com
.. _pip: http://www.pip-installer.org/
.. _PyPI: https://pypi.python.org/pypi/redock
.. _rsync: http://en.wikipedia.org/wiki/Rsync
.. _SSH: http://en.wikipedia.org/wiki/Secure_Shell
.. _update-dotdee: https://pypi.python.org/pypi/update-dotdee
.. _virtual environments: http://www.virtualenv.org/
.. _virtualization: http://en.wikipedia.org/wiki/Virtualization
