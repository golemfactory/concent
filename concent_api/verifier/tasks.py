import logging

from celery import shared_task

from .constants import VerificationResult


logger = logging.getLogger(__name__)


@shared_task
def verification_order_task(
    subtask_id:             str,
    src_code:               str,
    extra_data:             str,
    short_description:      str,
    working_directory:      str,
    performance:            str,
    docker_images:          str,
    source_file:            str,
    result_file:            str,
):
    verification_result_task.delay(

    )


@shared_task
def verification_result_task(
    subtask_id:         str,
    result:             VerificationResult,
    error_message:      str,
    error_code:         str,
):
    logger.info('verification_result_task starts with: SUBTASK_ID {} -- RESULT {}'.format(
        subtask_id,
        result,
    ))

    assert isinstance(subtask_id,       str)
    assert isinstance(error_message,    str)
    assert isinstance(error_code,       str)
    assert result in VerificationResult
    assert all([error_message, error_code]) if result == VerificationResult.ERROR else True

    logger.info('verification_result_task ends with: SUBTASK_ID {} -- RESULT {}'.format(
        subtask_id,
        result,
    ))
