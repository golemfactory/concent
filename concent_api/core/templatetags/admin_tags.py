from django import template
from constance import config
from core.models import Subtask

register = template.Library()


def get_active_subtasks():
    active_state_names = [state.name for state in Subtask.ACTIVE_STATES]
    return Subtask.objects.filter(state__in=active_state_names)


def get_result_uploaded_subtasks():
    return Subtask.objects.filter(state=Subtask.SubtaskState.RESULT_UPLOADED.name)  # pylint: disable=no-member


@register.assignment_tag
def get_shutdown_mode_state():
    return config.SOFT_SHUTDOWN_MODE


@register.assignment_tag
def get_active_subtasks_amount():
    return get_active_subtasks().count()


@register.assignment_tag
def get_active_subtasks_status():
    return get_result_uploaded_subtasks().exists()  # pylint: disable=no-member


@register.assignment_tag
def get_result_uploaded_subtasks_amount():
    return get_result_uploaded_subtasks().count()


@register.assignment_tag
def result_uploaded_subtasks_status():
    return not get_active_subtasks_status() and get_result_uploaded_subtasks_amount()
