from django.db.models import BinaryField
from django.db.models import BooleanField
from django.db.models import CharField
from django.db.models import DateTimeField
from django.db.models import ForeignKey
from django.db.models import PositiveSmallIntegerField
from django.db.models import Manager
from django.db.models import Model
from django.db.models import OneToOneField
from django.db.models import Q
from django.db.models import QuerySet

from utils.fields     import Base64Field
from utils.helpers    import is_base64

from .constants       import MESSAGE_TASK_ID_MAX_LENGTH


class StoredMessage(Model):
    type        = PositiveSmallIntegerField()
    timestamp   = DateTimeField()
    data        = BinaryField()
    task_id     = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH, null = True, blank = True)

    def __str__(self):
        return 'StoredMessage #{}, type:{}, {}'.format(self.id, self.type, self.timestamp)


class ReceiveStatusManager(Manager):

    def filter_public_key(self, client_public_key: str) -> QuerySet:
        """ Returns receive statuses matching client public. """
        assert is_base64(client_public_key)
        return self.filter(
            Q(message__auth__provider_public_key  = client_public_key) |
            Q(message__auth__requestor_public_key = client_public_key)
        )


class ReceiveStatus(Model):
    message     = ForeignKey(StoredMessage)
    timestamp   = DateTimeField()
    delivered   = BooleanField(default = False)

    objects = ReceiveStatusManager()

    def __str__(self):
        return 'ReceiveStatus #{}, message:{}'.format(self.id, self.message)

    class Meta:
        verbose_name        = ('Receive status')
        verbose_name_plural = ('Receive statuses')


class ReceiveOutOfBandStatus(Model):
    message     = ForeignKey(StoredMessage)
    timestamp   = DateTimeField()
    delivered   = BooleanField(default = False)

    def __str__(self):
        return 'ReceiveOutOfBandStatus #{}, message:{}'.format(self.id, self.message)

    class Meta:
        verbose_name        = ('ReceiveOutOfBand status')
        verbose_name_plural = ('ReceiveOutOfBand statuses')


class MessageAuth(Model):
    """
    This class is used to store provider and requestor keys for message exchange related to given initial message.
    """

    message              = OneToOneField(StoredMessage, related_name = 'auth')
    provider_public_key  = Base64Field(max_length=64)
    requestor_public_key = Base64Field(max_length=64)
