

class ReadOnlyMixin:
    """ Disables all editing capabilities. """

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def has_add_permission(self, _request, _obj = None):  # pylint: disable=no-self-use
        return False

    def has_change_permission(self, request, _obj=None):  # pylint: disable=no-self-use
        return request.method != 'POST'

    def has_delete_permission(self, _request, _obj = None):  # pylint: disable=no-self-use
        return False

    def save_model(self, request, obj, form, change):  # pylint: disable=no-self-use
        pass

    def delete_model(self, request, obj):  # pylint: disable=no-self-use
        pass

    def save_related(self, request, form, formsets, change):  # pylint: disable=no-self-use
        pass
