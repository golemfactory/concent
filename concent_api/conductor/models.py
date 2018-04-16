from django.core.validators import ValidationError
from django.db.models import CharField
from django.db.models import DateTimeField
from django.db.models import ForeignKey
from django.db.models import Model
from django.db.models import OneToOneField
from django.utils import timezone

from core.constants import MESSAGE_TASK_ID_MAX_LENGTH
from utils.fields import ChoiceEnum
from .constants import MESSAGE_PATH_LENGTH


class VerificationRequest(Model):

    subtask_id = CharField(max_length=MESSAGE_TASK_ID_MAX_LENGTH)

    # Relative path of the .zip file that contains Blender source files for the render.
    source_package_path = CharField(max_length=255, unique=True)

    # Relative path of the .zip file that contains the rendering result received from the provider.
    result_package_path = CharField(max_length=255, unique=True)

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
        JPG  = 'jpg'
        JPEG = 'jpeg'
        BMP  = 'bmp'
        SGI  = 'sgi'
        RGB  = 'rgb'
        BW   = 'bw'
        PNG  = 'PNG'
        JP2  = 'jp2'
        JP2C = 'jp2c'
        TGA  = 'tga'
        CIN  = 'cin'
        DPX  = 'dpx'
        HDR  = 'hdr'
        TIF  = 'tif'
        TIFF = 'tiff'

    # Foreign key to VerificationRequest. Can't be NULL and must be unique.
    verification_request = OneToOneField(VerificationRequest, unique=True, related_name='blender_subtask_definition')

    # Type of the output image to be produced by Blender. This determines the file extensions.
    # Only formats supported by Blender should be allowed here.
    # This value is passed to Blender using the -F command-line option.
    output_format = CharField(max_length=32, choices=OutputFormat.choices())

    # Relative path to the .blend file inside the source package.
    scene_file = CharField(max_length=MESSAGE_PATH_LENGTH)

    # Indicates when Conductor has received the request.
    created_at = DateTimeField(default=timezone.now)


class UploadReport(Model):
    """
    Existence of this object indicates that a file has been uploaded to nginx-storage
    and nginx notified Conductor about this fact.
    """

    # Relative path of the file. Relative to the same directory that paths listed in FileTransferTokens are relative to.
    path = CharField(max_length=MESSAGE_PATH_LENGTH)

    # Foreign key to VerificationRequest. Can be NULL if there's no corresponding request.
    verification_request = ForeignKey(VerificationRequest, related_name='upload_reports', blank=True, null=True)

    # Indicates when conductor has been notified about the upload.
    created_at      = DateTimeField(default=timezone.now)
