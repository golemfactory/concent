from django.contrib import admin
from django.db.models import Q

from common.admin import ModelAdminReadOnlyMixin
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from .models import PendingResponse
from .models import StoredMessage
from .models import Subtask


class ActivePassiveDownloadsStateFilter(admin.SimpleListFilter):
    title = 'Active/passive/downloads state'
    parameter_name = 'active_passive_state'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active'),
            ('passive', 'Passive'),
            ('active_downloads', 'Active with active downloads')
        )

    def queryset(self, request, queryset):
        active_state_names = [x.name for x in Subtask.ACTIVE_STATES]
        passive_state_names = [x.name for x in Subtask.PASSIVE_STATES]
        if self.value() == 'active':
            return queryset.filter(state__in=active_state_names)
        elif self.value() == 'passive':
            return queryset.filter(state__in=passive_state_names)
        elif self.value() == 'active_downloads':
            current_timestamp = get_current_utc_timestamp()
            return Subtask.objects_with_timing_columns.filter(
                Q(download_deadline__gte=current_timestamp, state=Subtask.SubtaskState.RESULT_UPLOADED.name) |  # pylint: disable=no-member
                Q(state__in=active_state_names)
            )
        return queryset


class SubtaskAdmin(ModelAdminReadOnlyMixin, admin.ModelAdmin):
    list_display = [
        'subtask_id',
        'task_id',
        'state',
        'get_provider_public_key',
        'get_requestor_public_key',
        'next_deadline',
        'computation_deadline',
        'download_deadline',
        'result_package_size',
    ]
    list_filter = (
        ActivePassiveDownloadsStateFilter,
        'state',
    )
    search_fields = [
        'provider__public_key',
        'requestor__public_key',
        'subtask_id',
        'task_id',
    ]

    def get_provider_public_key(self, obj):  # pylint: disable=no-self-use
        return obj.provider.public_key
    get_provider_public_key.short_description = 'Provider public key'  # type: ignore

    def get_requestor_public_key(self, obj):  # pylint: disable=no-self-use
        return obj.requestor.public_key
    get_requestor_public_key.short_description = 'Requestor public key'  # type: ignore

    def get_queryset(self, request):
        return Subtask.objects_with_timing_columns

    def download_deadline(self, obj):  # pylint: disable=no-self-use
        return parse_timestamp_to_utc_datetime(obj.download_deadline)
    download_deadline.short_description = 'Download deadline'  # type: ignore

class PendingResponseAdmin(ModelAdminReadOnlyMixin, admin.ModelAdmin):
    list_display = [
        'response_type',
        'queue',
        'get_subtask_subtask_id',
        'get_client_public_key',
        'delivered',
        'created_at',
    ]
    list_filter = (
        'delivered',
        'queue',
        'response_type',
    )
    search_fields = [
        'client__public_key',
        'subtask__subtask_id',
        'subtask__task_id',
    ]

    def get_subtask_subtask_id(self, obj):  # pylint: disable=no-self-use
        if obj.subtask is not None:
            return obj.subtask.subtask_id
        return '-not available-'
    get_subtask_subtask_id.short_description = 'Subtask id'  # type: ignore

    def get_client_public_key(self, obj):  # pylint: disable=no-self-use
        return obj.client.public_key
    get_client_public_key.short_description = 'Client public key'  # type: ignore


class StoredMessageAdmin(ModelAdminReadOnlyMixin, admin.ModelAdmin):

    list_display = [
        'type',
        'task_id',
        'subtask_id',
        'timestamp',
    ]
    list_filter = (
        'type',
    )
    search_fields = [
        'type',
        'task_id',
        'subtask_id',
    ]


admin.site.register(PendingResponse, PendingResponseAdmin)
admin.site.register(StoredMessage, StoredMessageAdmin)
admin.site.register(Subtask, SubtaskAdmin)
