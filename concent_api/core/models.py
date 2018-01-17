from django.db.models import BinaryField
from django.db.models import BooleanField
from django.db.models import CharField
from django.db.models import DateTimeField
from django.db.models import ForeignKey
from django.db.models import PositiveSmallIntegerField
from django.db.models import Model
from django.db.models import OneToOneField

from utils.fields     import Base64Field

from .constants       import MESSAGE_TASK_ID_MAX_LENGTH


class Message(Model):
    type        = PositiveSmallIntegerField()
    timestamp   = DateTimeField()
    data        = BinaryField()
    task_id     = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH, blank = False)

    def __str__(self):
        return 'Message #{}, type:{}, {}'.format(self.id, self.type, self.timestamp)


class ReceiveStatus(Model):
    message     = ForeignKey(Message)
    timestamp   = DateTimeField()
    delivered   = BooleanField(default = False)

    def __str__(self):
        return 'ReceiveStatus #{}, message:{}'.format(self.id, self.message)

    class Meta:
        verbose_name        = ('Receive status')
        verbose_name_plural = ('Receive statuses')


class ReceiveOutOfBandStatus(Model):
    message     = ForeignKey(Message)
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

    message              = OneToOneField(Message, related_name = 'auth')
    provider_public_key  = Base64Field(max_length=64)
    requestor_public_key = Base64Field(max_length=64)
