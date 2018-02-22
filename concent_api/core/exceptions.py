
class UnexpectedResponse(Exception):
    pass


class Http400(Exception):

    error_code = None

    def __init__(self, *args, **kwargs):
        assert 'error_code' in kwargs
        self.error_code = kwargs.pop('error_code')
        super().__init__(args, kwargs)
