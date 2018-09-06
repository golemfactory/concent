from django.forms import Form
from django.http.request import HttpRequest
from django.db.models import Model


class ModelAdminReadOnlyMixin:
    """ Disables all editing capabilities in subclasses of ModelAdmin class. """

    def get_actions(self, request: HttpRequest) -> dict:
        actions = super().get_actions(request)  # type: ignore
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def has_add_permission(self, _request: HttpRequest, _obj: Model=None) -> bool:  # pylint: disable=no-self-use
        return False

    def has_change_permission(self, request: HttpRequest, _obj: Model=None) -> bool:  # pylint: disable=no-self-use
        return request.method != 'POST'

    def has_delete_permission(self, _request: HttpRequest, _obj: Model=None) -> bool:  # pylint: disable=no-self-use
        return False

    def save_model(self, request: HttpRequest, obj: Model, form: Form, change: bool) -> None:  # pylint: disable=no-self-use
        pass

    def delete_model(self, request: HttpRequest, obj: Model) -> None:  # pylint: disable=no-self-use
        pass

    def save_related(self, request: HttpRequest, form: Form, formsets: list, change: bool) -> None:  # pylint: disable=no-self-use
        pass
