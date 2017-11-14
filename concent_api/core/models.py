from django.db.models import Model, CharField, IntegerField, DateTimeField, BooleanField, BinaryField, ForeignKey


class Message(Model):
    type        = CharField(max_length=32)
    timestamp   = DateTimeField()
    data        = BinaryField()
    task_id     = IntegerField(null=True)

    def __str__(self):
        return 'Message #{}, type:{}, {}'.format(self.id, self.type, self.timestamp)


class MessageStatus(Model):
    message     = ForeignKey('Message')
    timestamp   = DateTimeField()
    delivered   = BooleanField(default=False)

    def __str__(self):
        return 'MessageStatus #{}, message:{}, delivered:{}'.format(self.id, self.message, self.delivered)

    class Meta:
        verbose_name = ('Message status')
        verbose_name_plural = ('Message statuses')
