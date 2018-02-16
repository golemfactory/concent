from django.contrib import admin

from .models import StoredMessage
from .models import ReceiveStatus
from .models import ReceiveOutOfBandStatus


admin.site.register(StoredMessage)
admin.site.register(ReceiveStatus)
admin.site.register(ReceiveOutOfBandStatus)
