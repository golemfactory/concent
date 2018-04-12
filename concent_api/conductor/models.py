from django.db.models       import CharField
from django.db.models       import DateTimeField
from django.db.models       import ForeignKey
from django.db.models       import Model
from django.utils           import timezone

from core.constants         import MESSAGE_TASK_ID_MAX_LENGTH
from .constants             import MESSAGE_PATH_LENGTH


class VerificationRequest(Model):

    # Fields from ComputeTaskDef that we actually use.
    task_id                 = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH)
    subtask_id              = CharField(max_length = MESSAGE_TASK_ID_MAX_LENGTH)
    src_code                = CharField(max_length = 255, null = True, blank = True)
    extra_data              = CharField(max_length = 255, null = True, blank = True)
    short_description       = CharField(max_length = 255, null = True, blank = True)
    working_directory       = CharField(max_length = 255, null = True, blank = True)
    performance             = CharField(max_length = 255, null = True, blank = True)
    docker_images           = CharField(max_length = 255, null = True, blank = True)

    # Indicates when Conductor has received the request.
    created_at              = DateTimeField(default=timezone.now)


class UploadRequest(Model):
    """
    Existence of this object indicates that Concent is expecting a client to upload a specific file.
    """

    # Foreign key to VerificationRequest. Can't be NULL.
    verification_request = ForeignKey(VerificationRequest, related_name = 'upload_requests')

    # Relative path to the same directory that paths listed in FileTransferTokens are relative to. Must be unique.
    path                 = CharField(max_length = MESSAGE_PATH_LENGTH, unique = True)


class UploadReport(Model):
    """
    Existence of this object indicates that a file has been uploaded to nginx-storage
    and nginx notified Conductor about this fact.
    """

    # Relative path to the same directory that paths listed in FileTransferTokens are relative to.
    path            = CharField(max_length = MESSAGE_PATH_LENGTH)

    # Foreign key to UploadRequest. Can be NULL if there's no corresponding request.
    upload_request  = ForeignKey(UploadRequest, related_name = 'upload_reports', blank = True, null = True)

    # Indicates when conductor has been notified about the upload.
    created_at      = DateTimeField(default = timezone.now)
