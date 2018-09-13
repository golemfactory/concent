import datetime
from typing import Optional
from constance import config
from django import template
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Func
from django.db.models import IntegerField
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models import Value
from django.db.models.functions import Greatest
from common.helpers import parse_timestamp_to_utc_datetime
from common.helpers import get_current_utc_timestamp
from core.models import Subtask

register = template.Library()

ACTIVE_STATE_NAMES = [state.name for state in Subtask.ACTIVE_STATES]
PASSIVE_STATE_NAMES = [state.name for state in Subtask.PASSIVE_STATES]


def get_active_subtasks() -> QuerySet:
    current_timestamp = get_current_utc_timestamp()
    return Subtask.objects.filter(
        state__in=ACTIVE_STATE_NAMES,
        next_deadline__gte=parse_timestamp_to_utc_datetime(current_timestamp)
    )


def get_passive_with_downloads_subtasks() -> QuerySet:
    current_timestamp = get_current_utc_timestamp()
    return Subtask.objects_with_timing_columns.filter(
        download_deadline__gte=current_timestamp, state=Subtask.SubtaskState.RESULT_UPLOADED.name  # pylint: disable=no-member
    )


def get_longest_lasting_subtask_timestamp() -> Optional[int]:
    """Returns greatest value from 'next_deadline' and 'download_deadline' columns for Subtasks that are not timed out."""

    current_timestamp = get_current_utc_timestamp()
    filtered_subtasks = Subtask.objects_with_timing_columns.annotate(
        next_deadline_timestamp=ExpressionWrapper(
            Func(Value('epoch'), F('next_deadline'), function='DATE_PART'),
            output_field=IntegerField()
        )
    ).annotate(longest_lasting_subtask=Greatest('next_deadline_timestamp', 'download_deadline')).filter(
        Q(
            download_deadline__gte=current_timestamp,
            state=Subtask.SubtaskState.RESULT_UPLOADED.name,  # pylint: disable=no-member
        ) |
        Q(
            state__in=ACTIVE_STATE_NAMES,
            next_deadline_timestamp__gte=current_timestamp,
        )
    ).order_by('longest_lasting_subtask').last()
    if filtered_subtasks is not None:
        return filtered_subtasks.longest_lasting_subtask
    else:
        return None


@register.assignment_tag
def get_time_until_concent_can_be_shut_down() -> datetime.timedelta:
    current_timestamp = get_current_utc_timestamp()
    longest_lasting_subtask_timestamp = get_longest_lasting_subtask_timestamp()
    if longest_lasting_subtask_timestamp is None:
        return datetime.timedelta(0)
    else:
        return datetime.timedelta(seconds=longest_lasting_subtask_timestamp - current_timestamp)


@register.assignment_tag
def get_shutdown_mode_state() -> bool:
    return config.SOFT_SHUTDOWN_MODE


@register.assignment_tag
def get_active_subtasks_count() -> int:
    return get_active_subtasks().count()


@register.assignment_tag
def are_active_subtasks_present() -> bool:
    return get_active_subtasks().exists()  # pylint: disable=no-member


@register.assignment_tag
def get_subtasks_with_downloads_count() -> int:
    return get_passive_with_downloads_subtasks().count()


def are_downloads_subtasks_present() -> bool:
    return get_passive_with_downloads_subtasks().exists()  # pylint: disable=no-member


@register.assignment_tag
def are_only_with_downloads_subtasks_present() -> bool:
    return not are_active_subtasks_present() and are_downloads_subtasks_present()
