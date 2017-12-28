from django.conf import settings


class GolemMessagesVersionMiddleware(object):
    """
    Used to attach git tag or commit id of the golem_messages package
    currently used to HTTP response header.

    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Concent-Golem-Messages-Version'] = settings.GOLEM_MESSAGES_VERSION
        return response
