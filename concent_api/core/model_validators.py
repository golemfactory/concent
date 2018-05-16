import base64

from django.contrib.postgres.fields import JSONField
from django.core.validators import validate_ipv4_address
from django.core.validators import ValidationError
from django.db.models       import BinaryField
from django.db.models       import BooleanField
from django.db.models       import CharField
from django.db.models       import DateTimeField
from django.db.models       import DecimalField
from django.db.models       import IntegerField
from django.db.models       import ForeignKey
from django.db.models       import Model
from django.db.models       import OneToOneField
from django.db.models       import PositiveSmallIntegerField
from django.db.models       import PositiveIntegerField
from django.db.models       import TextField
from django.db.models       import Manager
from django.utils           import timezone

from constance              import config
from golem_messages         import message

from core.exceptions        import ConcentInSoftShutdownMode
from utils.fields           import Base64Field
from utils.fields           import ChoiceEnum

from .constants             import TASK_OWNER_KEY_LENGTH
from .constants             import ETHEREUM_ADDRESS_LENGTH
from .constants             import GOLEM_PUBLIC_KEY_LENGTH
from .constants             import HASH_FUNCTION
from .constants             import HASH_LENGTH
from .constants             import MESSAGE_TASK_ID_MAX_LENGTH
from .constants             import NUMBER_OF_ALL_PORTS



def validate_amount_paid(value):
    import ipdb; ipdb.set_trace()
    if not isinstance(value, int) or value < 0:
        raise ValidationError({
            'amount_paid': 'Amount paid must be an integer and bigger than or equal 0'
        })


# def validate_binary_key(value):
# 	if not len(value) == GOLEM_PUBLIC_KEY_LENGTH or not isinstance(value, bytes):
# 		raise ValidationError({
# 			'bytes_key'
# 		})