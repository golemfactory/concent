from django.contrib import admin

from utils.admin    import ModelAdminReadOnlyMixin
from .models        import PendingResponse
from .models        import StoredMessage
from .models        import Subtask


class ActivePassiveStateFilter(admin.SimpleListFilter):

    title          = 'Active/passive state'
    parameter_name = 'active_passive_state'

    def lookups(self, request, model_admin):
        return (
            ('active',  'Active'),
            ('passive', 'Passive'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            active_state_names = [x.name for x in Subtask.ACTIVE_STATES]
            return queryset.filter(state__in=active_state_names)
        elif self.value() == 'passive':
            passive_state_names = [x.name for x in Subtask.PASSIVE_STATES]
            return queryset.filter(state__in=passive_state_names)
        return queryset


class SubtaskAdmin(ModelAdminReadOnlyMixin, admin.ModelAdmin):

    list_display = [
        'subtask_id',
        'task_id',
        'state',
        'get_provider_public_key',
        'get_requestor_public_key',
        'next_deadline',
    ]
    list_filter = (
        ActivePassiveStateFilter,
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
        return obj.provider.public_key
    get_requestor_public_key.short_description = 'Requestor public key'  # type: ignore


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


admin.site.register(PendingResponse, PendingResponseAdmin)
admin.site.register(StoredMessage)
admin.site.register(Subtask, SubtaskAdmin)
