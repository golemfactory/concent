from common.exceptions import ConcentBaseException


class UnexpectedResponse(Exception):
    pass


class Http400(ConcentBaseException):
    pass


class FileTransferTokenError(ConcentBaseException):
    pass


class HashingAlgorithmError(ConcentBaseException):
    pass


class GolemMessageValidationError(ConcentBaseException):
    pass


class FrameNumberValidationError(ConcentBaseException):
    pass


class TransactionNonceMismatch(Exception):
    pass


class SceneFilePathError(ConcentBaseException):
    pass


class SCICallbackError(Exception):
    pass


class SCICallbackTimeoutError(SCICallbackError):
    pass


class SCICallbackRequestIdError(SCICallbackError):
    pass


class SCICallbackPayloadError(SCICallbackError):
    pass


class SCICallbackFrameError(SCICallbackError):
    pass


class SCICallbackTransactionSignatureError(SCICallbackError):
    pass


class SCICallbackPayloadSignatureError(SCICallbackError):
    pass
