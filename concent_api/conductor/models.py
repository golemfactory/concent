from django.core.validators import MaxLengthValidator
from django.core.validators import ValidationError
from django.db.models import BooleanField
from django.db.models import CharField
from django.db.models import DateTimeField
from django.db.models import ForeignKey
from django.db.models import Model
from django.db.models import OneToOneField
from django.db.models import PositiveIntegerField
from django.db.models import TextField
from django.utils import timezone

from core.constants import MESSAGE_TASK_ID_MAX_LENGTH
from common.fields import ChoiceEnum
from .constants import MESSAGE_PATH_LENGTH


class VerificationRequest(Model):

    subtask_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)

    # Relative path of the .zip file that contains Blender source files for the render.
    source_package_path = TextField(validators=[MaxLengthValidator(MESSAGE_PATH_LENGTH)], unique=True)

    # Relative path of the .zip file that contains the rendering result received from the provider.
    result_package_path = TextField(validators=[MaxLengthValidator(MESSAGE_PATH_LENGTH)], unique=True)

    # True when `upload_finished` task for this subtask has already been sent to the work queue.
    upload_finished = BooleanField(default=False)

    # True when `upload_acknowledged` task for this subtask has already been processed.
    upload_acknowledged = BooleanField(default=False)

    # Deadline on additional verification for related Subtask.
    verification_deadline = DateTimeField()

    # Indicates when Conductor has received the request.
    created_at = DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()

        # source_package_path cannot be used as result_package_path in any model instance.
        if VerificationRequest.objects.filter(result_package_path=self.source_package_path).exists():
            raise ValidationError({
                'source_package_path': 'source_package_path cannot be used as result_package_path in any other VerificationRequest.'
            })

        # result_package_path cannot be used as source_package_path in any model instance.
        if VerificationRequest.objects.filter(source_package_path=self.result_package_path).exists():
            raise ValidationError({
                'result_package_path': 'result_package_path cannot be used as source_package_path in any other VerificationRequest.'
            })


class BlenderSubtaskDefinition(Model):
    """
    For each VerificationRequest there must be exactly one BlenderSubtaskDefinition in the database.
    """

    class OutputFormat(ChoiceEnum):
        JPG = 'jpg'
        PNG = 'png'
        EXR = 'exr'

    # Foreign key to VerificationRequest. Can't be NULL and must be unique.
    verification_request = OneToOneField(VerificationRequest, unique=True, related_name='blender_subtask_definition')

    # Type of the output image to be produced by Blender. This determines the file extensions.
    # Only formats supported by Blender should be allowed here.
    # This value is passed to Blender using the -F command-line option.
    output_format = CharField(max_length=32, choices=OutputFormat.choices())

    # Relative path to the .blend file inside the source package.
    scene_file = CharField(max_length=MESSAGE_PATH_LENGTH)

    # Source code of the Python script to be executed by Blender.
    blender_crop_script = TextField(blank=True, null=True)


class UploadReport(Model):
    """
    Existence of this object indicates that a file has been uploaded to nginx-storage
    and nginx notified Conductor about this fact.
    """

    # Relative path of the file. Relative to the same directory that paths listed in FileTransferTokens are relative to.
    path = TextField(validators=[MaxLengthValidator(MESSAGE_PATH_LENGTH)])

    # Foreign key to VerificationRequest. Can be NULL if there's no corresponding request.
    verification_request = ForeignKey(VerificationRequest, related_name='upload_reports', blank=True, null=True)

    # Indicates when conductor has been notified about the upload.
    created_at      = DateTimeField(default=timezone.now)


class Frame(Model):
    """
    Every frame which needs to be render by Concent must be stored in this model
    For one BlenderSubtaskDefinition can be a lot Frame objects; BlenderSubtaskDefinition must be unique with Frame
    """

    blender_subtask_definition = ForeignKey(BlenderSubtaskDefinition, related_name='frames')

    number = PositiveIntegerField()

    class Meta:
        unique_together = (
            ('blender_subtask_definition', 'number'),
        )
