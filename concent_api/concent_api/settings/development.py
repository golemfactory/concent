# pylint: disable=unused-wildcard-import
from .base import *  # NOQA  # pylint: disable=wildcard-import

SECRET_KEY = 'testkey'

DEBUG = True

DATABASES['default']['USER']     = 'postgres'
DATABASES['default']['PASSWORD'] = ''

CONCENT_PUBLIC_KEY  = b'\xf3\x97\x19\xcdX\xda\x86tiP\x1c&\xd39M\x9e\xa4\xddb\x89\xb5,]O\xd5cR\x84\xb85\xed\xc9\xa17e,\xb2s\xeb\n1\xcaN.l\xba\xc3\xb7\xc2\xba\xff\xabN\xde\xb3\x0b\xa6l\xbf6o\x81\xe0;'
CONCENT_PRIVATE_KEY = b'l\xcdh\x19\xeb$>\xbcG\xa1\xc7v\xe8\xd7o\x0c\xbf\x0e\x0fM\x89lw\x1e\xd7K\xd6Hnv$\xa2'

CONCENT_FEATURES = [
    "concent-api",
    "gatekeeper",
    "admin-panel",
]

# URL format: 'protocol://<user>:<password>@<hostname>:<port>/<virtual host>'
CELERY_BROKER_URL = 'amqp://localhost:5672'

STORAGE_CLUSTER_ADDRESS = 'http://devel.concent.golem.network/'

GETH_CONTAINER_ADDRESS = 'http://localhost:8545'
