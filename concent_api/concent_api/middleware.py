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
