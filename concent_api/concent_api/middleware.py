import os

from django.conf    import settings

from golem_messages import __version__


class GolemMessagesVersionMiddleware(object):
    """
    Used to attach version of the golem_messages package currently used to HTTP response header.

    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Concent-Golem-Messages-Version'] = __version__
        return response


class ConcentVersionMiddleware(object):
    """
    Used to attach version of the Concent currently used to HTTP response header.

    """

    _concent_version = None

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._concent_version is None:
            with open(os.path.join(settings.BASE_DIR, '..', 'RELEASE-VERSION')) as f:
                self._concent_version = f.read()

        response = self.get_response(request)
        response['Concent-Version'] = self._concent_version
        return response
