from enum import Enum
import logging

from celery import shared_task

from .constants import VerificationResult


logger = logging.getLogger(__name__)


@shared_task
def blender_verification_order(
    subtask_id:             str,
    source_package_path:    str,  # pylint: disable=unused-argument
    result_package_path:    str,  # pylint: disable=unused-argument
    output_format:          Enum,  # pylint: disable=unused-argument
    scene_file:             str,  # pylint: disable=unused-argument
):
    verification_result.delay(
        subtask_id,
        VerificationResult.MATCH,
    )


@shared_task
def verification_result(
    subtask_id:     str,
    result:         VerificationResult,
    error_message:  str,
    error_code:     str,
):
    logger.info(
        'verification_result_task starts with: SUBTASK_ID {} -- RESULT {}'.format(
            subtask_id,
            result,
        )
    )

    assert isinstance(subtask_id, str)
    assert isinstance(error_message, str)
    assert isinstance(error_code, str)
    assert result in VerificationResult
    assert all([error_message, error_code]) if result == VerificationResult.ERROR else True

    logger.info(
        'verification_result_task ends with: SUBTASK_ID {} -- RESULT {}'.format(
            subtask_id,
            result,
        )
    )
