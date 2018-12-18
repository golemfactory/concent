import datetime
from decimal import Decimal
from django.contrib import admin
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http.request import HttpRequest
from common.admin import ModelAdminReadOnlyMixin
from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from .models import DepositAccount
from .models import DepositClaim
from .models import GlobalTransactionState
from .models import PendingResponse
from .models import StoredMessage
from .models import Subtask
from .models import SubtaskWithTimingColumnsManager

ACTIVE_STATE_NAMES = [x.name for x in Subtask.ACTIVE_STATES]
PASSIVE_STATE_NAMES = [x.name for x in Subtask.PASSIVE_STATES]


class ActivePassiveDownloadsStateFilter(admin.SimpleListFilter):
    title = 'Active/passive/downloads state'
    parameter_name = 'active_passive_state'

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> tuple:
        return (
            ('active', 'Not timed out active'),
            ('passive', 'Passive or timed out active'),
            ('active_or_downloads', 'Not timed out active or active with pending downloads')
        )

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
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
    def get_provider_public_key(cls, subtask: Subtask) -> str:
        return subtask.provider.public_key
    get_provider_public_key.short_description = 'Provider public key'  # type: ignore

    @classmethod
    def get_requestor_public_key(cls, subtask: Subtask) -> str:
        return subtask.requestor.public_key
    get_requestor_public_key.short_description = 'Requestor public key'  # type: ignore

    @classmethod
    def get_queryset(cls, request: HttpRequest) -> SubtaskWithTimingColumnsManager:
        return Subtask.objects_with_timing_columns

    @classmethod
    def download_deadline(cls, subtask: Subtask) -> datetime.datetime:
        return parse_timestamp_to_utc_datetime(subtask.download_deadline)
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
    def get_subtask_subtask_id(cls, pending_response: PendingResponse) -> str:
        if pending_response.subtask is not None:
            return pending_response.subtask.subtask_id
        return '-not available-'
    get_subtask_subtask_id.short_description = 'Subtask id'  # type: ignore

    @classmethod
    def get_client_public_key(cls, pending_response: PendingResponse) -> str:
        return pending_response.client.public_key
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


class DepositAccountAdmin(ModelAdminReadOnlyMixin, admin.ModelAdmin):

    list_display = [
        'client_public_key',
        'ethereum_address',
        'created_at',
        'get_sum_of_claims',
    ]
    search_fields = [
        'client__public_key',
        'ethereum_address',
    ]

    @classmethod
    def client_public_key(cls, deposit_account: DepositAccount) -> str:
        return deposit_account.client.public_key
    client_public_key.short_description = 'Client'  # type: ignore

    def get_sum_of_claims(self, deposit_account: DepositAccount) -> Decimal:  # pylint: disable=no-self-use
        return deposit_account.sum_of_claims
    get_sum_of_claims.short_description = 'Sum of related DepositClaims'  # type: ignore
    get_sum_of_claims.admin_order_field = 'sum_of_claims'  # type: ignore

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).annotate(sum_of_claims=Coalesce(Sum('depositclaim__amount'), 0))


class DepositClaimAdmin(admin.ModelAdmin):

    list_display = [
        'subtask_id',
        'payer_deposit_account_ethereum_address',
        'payee_ethereum_address',
        'concent_use_case',
        'amount',
        'tx_hash',
        'created_at',
        'modified_at',
    ]
    list_filter = [
        'concent_use_case',
    ]
    search_fields = [
        'subtask_id',
        'payer_deposit_account__ethereum_address',
        'payee_ethereum_address',
        'tx_hash',
    ]

    @classmethod
    def payer_deposit_account_ethereum_address(cls, deposit_claim: DepositClaim) -> str:
        return deposit_claim.payer_deposit_account.ethereum_address
    payer_deposit_account_ethereum_address.short_description = 'Payer ethereum address'  # type: ignore


admin.site.register(DepositAccount, DepositAccountAdmin)
admin.site.register(DepositClaim, DepositClaimAdmin)
admin.site.register(PendingResponse, PendingResponseAdmin)
admin.site.register(StoredMessage, StoredMessageAdmin)
admin.site.register(Subtask, SubtaskAdmin)
admin.site.register(GlobalTransactionState)
