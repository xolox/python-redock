redock: A human friendly wrapper around Docker
==============================================

The ``redock`` program is a human friendly wrapper around Docker_, the `Linux
container engine`_. Docker implements an extremely lightweight form of
virtualization_ that makes it possible to start and stop virtual machines in
less than a second, opening exciting new possibilities for testing e.g.
automated deployment systems where this would previously have required far more
resources.

Usage
-----

You will need to have Docker_ installed before you can use ``redock``, please
refer to Docker's `installation instructions`_. After you've installed Docker
you can install ``redock`` using the following command::

    $ pip install redock

Once you've installed the program, here's how you create a container::

    $ redock whatever-name-you-like

You should now be able to connect to the container using SSH_::

    $ ssh whatever-name-you-like

This works because your ``~/.ssh/config`` has been updated to include a host
definition for the container. This means you can also connect using rsync_ or
anything else which works on top of SSH_.

Contact
-------

The latest version of ``redock`` is available on PyPi_ and GitHub_. For bug
reports please create an issue on GitHub_. If you have questions, suggestions,
etc. feel free to send me an e-mail at `peter@peterodding.com`_.

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
.. _PyPi: https://pypi.python.org/pypi/redock
.. _rsync: http://en.wikipedia.org/wiki/Rsync
.. _SSH: http://en.wikipedia.org/wiki/Secure_Shell
.. _virtualization: http://en.wikipedia.org/wiki/Virtualization
