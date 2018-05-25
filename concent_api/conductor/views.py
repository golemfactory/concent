from django.http.response import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from utils.decorators import provides_concent_feature
from verifier.tasks import blender_verification_order
from .models import UploadReport
from .models import VerificationRequest


@provides_concent_feature('conductor-urls')
@csrf_exempt
def report_upload(_request, file_path):

    # If there's a corresponding VerificationRequest, the load it and link it to UploadReport.
    try:
        verification_request = VerificationRequest.objects.get(
            source_package_path = file_path
        )
    except VerificationRequest.DoesNotExist:
        verification_request = None

    # The app creates a new instance of UploadReport in the database.
    upload_report_obj = UploadReport(
        path = file_path,
        verification_request = verification_request,
    )
    upload_report_obj.full_clean()
    upload_report_obj.save()

    # The app gets the VerificationRequest and checks if both source and result packages have reports.
    if (
        verification_request is not None and
        verification_request.blender_subtask_definition is not None and
        verification_request.upload_reports.filter(path=verification_request.source_package_path).exists() and
        verification_request.upload_reports.filter(path=verification_request.result_package_path).exists()
    ):
        # If all expected files have been uploaded, the app sends blender_verification_order task to the work queue.
        blender_verification_order.delay(
            verification_request.subtask_id,
            verification_request.source_package_path,
            verification_request.result_package_path,
            verification_request.blender_subtask_definition.output_format,
            verification_request.blender_subtask_definition.scene_file,
        )

    return HttpResponse()
