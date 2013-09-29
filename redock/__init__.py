# Semi-standard module versioning.
__version__ = '0.5.8'

# Silence the logger of an external dependency.
import logging
logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(logging.WARN)
