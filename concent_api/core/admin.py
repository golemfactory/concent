from django.contrib import admin

from .models import Message, ReceiveStatus, ReceiveOutOfBandStatus


admin.site.register(Message)
admin.site.register(ReceiveStatus)
admin.site.register(ReceiveOutOfBandStatus)
