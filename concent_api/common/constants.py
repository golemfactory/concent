import enum


class ConcentUseCase(enum.IntEnum):
    """ Represents use cases handled by Concent application. """

    FORCED_REPORT           = 1
    FORCED_TASK_RESULT      = 2
    FORCED_ACCEPTANCE       = 3
    ADDITIONAL_VERIFICATION = 4
    FORCED_PAYMENT          = 5


class ErrorCode(enum.Enum):
    AUTH_CLIENT_AUTH_MESSAGE_MISSING                                    = 'header.client_public_key.missing'
    AUTH_CLIENT_AUTH_MESSAGE_INVALID                                    = 'header.client_public_key.invalid'
    CONCENT_APPLICATION_CRASH                                           = 'concent.application_crash'
    CONDUCTOR_VERIFICATION_REQUEST_ALREADY_ACKNOWLEDGED                 = 'conductor.verification_request_already_acknowledged'
    CONDUCTOR_VERIFICATION_REQUEST_ALREADY_INITIATED                    = 'conductor.verification_request_already_initiated'
    HEADER_AUTHORIZATION_MISSING                                        = 'header.authorization.missing'
    HEADER_AUTHORIZATION_MISSING_TOKEN                                  = 'header.authorization.missing_token'
    HEADER_AUTHORIZATION_TOKEN_INVALID_MESSAGE                          = 'header.authorization.token_not_valid_message'
    HEADER_AUTHORIZATION_UNRECOGNIZED_SCHEME                            = 'header.authorization.unrecognized_scheme'
    HEADER_AUTHORIZATION_NOT_BASE64_ENCODED_VALUE                       = 'header.authorization.not_base64_encoded_value'
    HEADER_CONTENT_TYPE_NOT_SUPPORTED                                   = 'header.content_type.not_supported'
    HEADER_PROTOCOL_VERSION_UNSUPPORTED                                 = 'header.protocol_version.unsupported'
    MESSAGE_AUTHORIZED_CLIENT_PUBLIC_KEY_UNAUTHORIZED_CLIENT            = 'message.authorized_client_public_key_unauthorized_client'
    MESSAGE_AUTHORIZED_CLIENT_PUBLIC_KEY_WRONG_TYPE                     = 'message.authorized_client_public_key_wrong_type'
    MESSAGE_FILES_CATEGORY_MISSING                                      = 'message.files.category.empty'
    MESSAGE_FILES_CATEGORY_INVALID                                      = 'message.files.category.invalid'
    MESSAGE_FILES_CATEGORY_NOT_UNIQUE                                   = 'message.files.category.not_unique'
    MESSAGE_FILES_CHECKSUM_EMPTY                                        = 'message.files.checksum.empty'
    MESSAGE_FILES_CHECKSUM_INVALID_SHA1_HASH                            = 'message.files.checksum.invalid_sha1_hash'
    MESSAGE_FILES_CHECKSUM_INVALID_ALGORITHM                            = 'message.files.checksum.invalid_algorithm'
    MESSAGE_FILES_CHECKSUM_WRONG_FORMAT                                 = 'message.files.checksum.wrong_format'
    MESSAGE_FILES_CHECKSUM_WRONG_TYPE                                   = 'message.files.checksum.wrong_type'
    MESSAGE_FILES_PATH_NOT_LISTED_IN_FILES                              = 'message.files.path.not_listed_in_files'
    MESSAGE_FILES_PATHS_NOT_UNIQUE                                      = 'message.files.paths.not_unique'
    MESSAGE_FILES_SIZE_EMPTY                                            = 'message.files.size.empty'
    MESSAGE_FILES_SIZE_NEGATIVE                                         = 'message.files.size.negative'
    MESSAGE_FILES_SIZE_WRONG_TYPE                                       = 'message.files.size.wrong_type'
    MESSAGE_FILES_WRONG_TYPE                                            = 'message.files.wrong_type'
    MESSAGE_FRAME_WRONG_TYPE                                            = 'message.frames.wrong_type'
    MESSAGE_FRAME_VALUE_NOT_POSITIVE_INTEGER                            = 'message.frames.value_not_positive_integer'
    MESSAGE_INVALID                                                     = 'message.invalid'
    MESSAGE_WRONG_UUID_VALUE                                            = 'message.wrong_uuid_value'
    MESSAGE_WRONG_UUID_TYPE                                             = 'message.wrong_uuid_type'
    MESSAGE_OPERATION_INVALID                                           = 'message.operation.invalid'
    MESSAGE_SIGNATURE_MISSING                                           = 'message.signature.missing'
    MESSAGE_SIGNATURE_WRONG                                             = 'message.signature.wrong'
    MESSAGE_STORAGE_CLUSTER_INVALID_URL                                 = 'message.storage_cluster_invalid_url'
    MESSAGE_STORAGE_CLUSTER_WRONG_CLUSTER                               = 'message.storage_cluster_wrong_cluster'
    MESSAGE_STORAGE_CLUSTER_WRONG_TYPE                                  = 'message.storage_cluster_wrong_type'
    MESSAGE_TIMESTAMP_TOO_OLD                                           = 'message.timestamp.too_old'
    MESSAGE_TOKEN_EXPIRATION_DEADLINE_PASSED                            = 'message.token_expiration_deadline_passed'
    MESSAGE_TOKEN_EXPIRATION_DEADLINE_WRONG_TYPE                        = 'message.token_expiration_deadline_wrong_type'
    MESSAGE_UNABLE_TO_DESERIALIZE                                       = 'message.unable_to_deserialize'
    MESSAGE_UNEXPECTED                                                  = 'message.unexpected'
    MESSAGE_UNKNOWN                                                     = 'message.unknown'
    MESSAGE_WRONG_FIELDS                                                = 'message.wrong_fields'
    MESSAGE_VALUE_BLANK                                                 = 'message.value_blank'
    MESSAGE_VALUE_NEGATIVE                                              = 'message.value_negative'
    MESSAGE_VALUE_NOT_ALLOWED                                           = 'message.value_not_allowed'
    MESSAGE_VALUE_NOT_INTEGER                                           = 'message.value_not_integer'
    MESSAGE_VALUE_NOT_STRING                                            = 'message.value_not_string'
    MESSAGE_VALUE_WRONG_LENGTH                                          = 'message.value_wrong_length'
    MESSAGE_VALUE_WRONG_TYPE                                            = 'message.value_wrong_type'
    MESSAGES_NOT_IDENTICAL                                              = 'messages.not_identical'
    QUEUE_COMMUNICATION_NOT_STARTED                                     = 'queue.communication_not_started'
    QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH                                 = 'queue.requestor_public_key_mismatch'
    QUEUE_SUBTASK_ID_MISMATCH                                           = 'queue.subtask_id_mismatch'
    QUEUE_SUBTASK_STATE_TRANSITION_NOT_ALLOWED                          = 'queue.subtask_state_transition_not_allowed'
    QUEUE_TIMEOUT                                                       = 'queue.timeout'
    QUEUE_WRONG_STATE                                                   = 'queue.wrong_state'
    REQUEST_BODY_NOT_EMPTY                                              = 'request_body.not_empty'
    SCI_NOT_SYNCHRONIZED                                                = 'sci.not_synchronized'
    SUBTASK_DUPLICATE_REQUEST                                           = 'subtask.duplicate_request'
    UNSUPPORTED_PROTOCOL_VERSION                                        = 'concent.unsupported_protocol_version'
    VERIFIER_COMPUTING_SSIM_FAILED                                     = 'verifier.computing_ssim_failed'
    VERIFIER_FILE_DOWNLOAD_FAILED                                      = 'verifier.file_download_failed'
    VERIFIER_LOADING_FILES_INTO_MEMORY_FAILED                          = 'verifier.loading_files_into_memory_failed'
    VERIFIER_LOADING_FILES_WITH_OPENCV_FAILED                          = 'verifier.loading_files_with_opencv_failed'
    VERIFIER_RUNNING_BLENDER_FAILED                                    = 'verifier.running_blender_failed'
    VERIFIER_UNPACKING_ARCHIVE_FAILED                                  = 'verifier.unpacking_archive_failed'


class MessageIdField(enum.Enum):
    TASK_ID = 'task_id'
    SUBTASK_ID = 'subtask_id'


ERROR_IN_GOLEM_MESSAGE = 'Error in Golem Message.'
