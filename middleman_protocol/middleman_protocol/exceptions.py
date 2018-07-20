class MiddlemanProtocolError(Exception):
    pass


class PayloadTypeInvalidMiddlemanProtocolError(MiddlemanProtocolError):
    pass


class RequestIdInvalidTypeMiddlemanProtocolError(MiddlemanProtocolError):
    pass


class SignatureInvalidMiddlemanProtocolError(MiddlemanProtocolError):
    pass


class PayloadInvalidMiddlemanProtocolError(MiddlemanProtocolError):
    pass


class FrameInvalidMiddlemanProtocolError(MiddlemanProtocolError):
    pass


class BrokenEscapingInFrameMiddlemanProtocolError(MiddlemanProtocolError):
    pass
