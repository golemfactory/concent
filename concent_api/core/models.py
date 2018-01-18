from django.db.models import BinaryField
from django.db.models import BooleanField
from django.db.models import DateTimeField
from django.db.models import ForeignKey
from django.db.models import IntegerField
from django.db.models import PositiveSmallIntegerField
from django.db.models import Model


class Message(Model):
    type        = PositiveSmallIntegerField()
    timestamp   = DateTimeField()
    data        = BinaryField()
    task_id     = IntegerField(null = True)

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
