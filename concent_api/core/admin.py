from django.contrib import admin
from django.db.models import Q
from django.db.models import QuerySet
from common.admin import ModelAdminReadOnlyMixin
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from .models import PendingResponse
from .models import StoredMessage
from .models import Subtask

ACTIVE_STATE_NAMES = [x.name for x in Subtask.ACTIVE_STATES]
PASSIVE_STATE_NAMES = [x.name for x in Subtask.PASSIVE_STATES]


class ActivePassiveDownloadsStateFilter(admin.SimpleListFilter):
    title = 'Active/passive/downloads state'
    parameter_name = 'active_passive_state'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Not timed out active'),
            ('passive', 'Passive or timed out active'),
            ('active_or_downloads', 'Not timed out active or active with pending downloads')
        )

    def queryset(self, request, queryset: QuerySet) -> QuerySet:
        assert self.value() in {'active', 'passive', 'active_or_downloads', None}
        current_timestamp = get_current_utc_timestamp()
        if self.value() == 'active':
            return queryset.filter(state__in=ACTIVE_STATE_NAMES, next_deadline__gte=parse_timestamp_to_utc_datetime(current_timestamp))
        elif self.value() == 'passive':
            return queryset.filter(
                Q(state__in=PASSIVE_STATE_NAMES) |
                Q(state__in=ACTIVE_STATE_NAMES, next_deadline__lt=parse_timestamp_to_utc_datetime(current_timestamp))
            )
        elif self.value() == 'active_or_downloads':
            return Subtask.objects_with_timing_columns.filter(
                Q(download_deadline__gte=current_timestamp, state=Subtask.SubtaskState.RESULT_UPLOADED.name) |  # pylint: disable=no-member
                Q(state__in=ACTIVE_STATE_NAMES, next_deadline__gte=parse_timestamp_to_utc_datetime(current_timestamp))
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
        'created_at',
        'modified_at',
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

    @classmethod
    def get_provider_public_key(cls, obj):
        return obj.provider.public_key
    get_provider_public_key.short_description = 'Provider public key'  # type: ignore

    @classmethod
    def get_requestor_public_key(cls, obj):
        return obj.requestor.public_key
    get_requestor_public_key.short_description = 'Requestor public key'  # type: ignore

    @classmethod
    def get_queryset(cls, request):
        return Subtask.objects_with_timing_columns

    @classmethod
    def download_deadline(cls, obj):
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

    @classmethod
    def get_subtask_subtask_id(cls, obj):
        if obj.subtask is not None:
            return obj.subtask.subtask_id
        return '-not available-'
    get_subtask_subtask_id.short_description = 'Subtask id'  # type: ignore

    @classmethod
    def get_client_public_key(cls, obj):
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
