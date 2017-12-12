from django.contrib import admin

from .models import Message, MessageStatus


admin.site.register(Message)
admin.site.register(MessageStatus)
