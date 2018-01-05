from django.contrib import admin

from .models import Message
from .models import ReceiveStatus
from .models import ReceiveOutOfBandStatus


admin.site.register(Message)
admin.site.register(ReceiveStatus)
admin.site.register(ReceiveOutOfBandStatus)
