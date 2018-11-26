from base64 import b64encode
from logging import getLogger
from typing import Any
from typing import Optional
from typing import Tuple
from typing import Union
from copy import copy

from django.conf import settings
from django.core.mail import mail_admins
from django.db import IntegrityError
from django.db import transaction
from django.http import HttpResponse

from constance import config

from golem_messages import message
from golem_messages.message.concents import AckForceGetTaskResult
from golem_messages.message.concents import FileTransferToken
from golem_messages.message.concents import ForceGetTaskResult
from golem_messages.message.concents import ForceGetTaskResultRejected
from golem_messages.message.concents import ForcePaymentCommitted
from golem_messages.message.concents import ForcePaymentRejected
from golem_messages.message.concents import ForceReportComputedTask
from golem_messages.message.concents import ForceReportComputedTaskResponse
from golem_messages.message.concents import ServiceRefused
from golem_messages.message.tasks import SubtaskResultsRejected
from golem_messages.register import library

from common.constants import ConcentUseCase
from common.constants import ErrorCode
from common.exceptions import ConcentInSoftShutdownMode
from common.helpers import deserialize_message
from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import parse_datetime_to_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.helpers import sign_message
from common.logging import convert_public_key_to_hex
from common.logging import log
from common.validations import validate_secure_hash_algorithm
from common import logging
from conductor.tasks import result_transfer_request
from core.exceptions import BanksterTimestampError
from core.exceptions import CreateModelIntegrityError
from core.exceptions import Http400
from core.exceptions import TooSmallProviderDeposit
from core.models import Client
from core.models import PaymentInfo
from core.models import PendingResponse
from core.models import StoredMessage
from core.models import Subtask
from core.payments import bankster
from core.queue_operations import send_blender_verification_request
from core.subtask_helpers import are_keys_and_addresses_unique_in_message_subtask_results_accepted
from core.subtask_helpers import are_subtask_results_accepted_messages_signed_by_the_same_requestor
from core.subtask_helpers import delete_deposit_claim
from core.subtask_helpers import get_one_or_none
from core.subtask_helpers import is_state_transition_possible
from core.transfer_operations import create_file_transfer_token_for_golem_client
from core.transfer_operations import create_file_transfer_token_for_verification_use_case
from core.transfer_operations import store_pending_message
from core.utils import calculate_concent_verification_time
from core.utils import calculate_maximum_download_time
from core.utils import calculate_subtask_verification_time
from core.utils import is_protocol_version_compatible
from core.validation import is_golem_message_signed_with_key
from core.validation import substitute_new_report_computed_task_if_needed
from core.validation import validate_that_golem_messages_are_signed_with_key
from core.validation import validate_reject_report_computed_task
from core.validation import validate_all_messages_identical
from core.validation import validate_ethereum_addresses
from core.validation import validate_golem_message_subtask_results_rejected
from core.validation import validate_report_computed_task_time_window
from core.validation import validate_task_to_compute

from .utils import hex_to_bytes_convert

logger = getLogger(__name__)


def handle_send_force_report_computed_task(
    client_message: ForceReportComputedTask
) -> Union[HttpResponse, ForceReportComputedTaskResponse]:
    task_to_compute = client_message.report_computed_task.task_to_compute
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)

    validate_secure_hash_algorithm(client_message.report_computed_task.package_hash)
    validate_that_golem_messages_are_signed_with_key(
        provider_public_key,
        client_message.report_computed_task,
        task_to_compute.want_to_compute_task
    )
    validate_task_to_compute(task_to_compute)
    validate_report_computed_task_time_window(client_message.report_computed_task)
    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        task_to_compute,
    )

    if Subtask.objects.filter(  # pylint: disable=no-member
        subtask_id=task_to_compute.compute_task_def['subtask_id'],
    ).exists():
        raise Http400(
            "{} is already being processed for this task.".format(type(client_message).__name__),
            error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST,
        )

    if task_to_compute.compute_task_def['deadline'] < get_current_utc_timestamp():
        logging.log_timeout(
            logger,
            client_message,
            provider_public_key,
            task_to_compute.compute_task_def['deadline'],
        )
        return message.concents.ForceReportComputedTaskResponse(
            reason=message.concents.ForceReportComputedTaskResponse.REASON.SubtaskTimeout
        )
    with transaction.atomic(using='control'):
        subtask = store_subtask(
            task_id=task_to_compute.compute_task_def['task_id'],
            subtask_id=task_to_compute.compute_task_def['subtask_id'],
            provider_public_key=provider_public_key,
            requestor_public_key=requestor_public_key,
            state=Subtask.SubtaskState.FORCING_REPORT,
            next_deadline=int(task_to_compute.compute_task_def['deadline']) + settings.CONCENT_MESSAGING_TIME,
            task_to_compute=task_to_compute,
            report_computed_task=client_message.report_computed_task,
        )
        store_pending_message(
            response_type=PendingResponse.ResponseType.ForceReportComputedTask,
            client_public_key=requestor_public_key,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )
    logging.log_message_added_to_queue(
        logger,
        client_message,
        provider_public_key,
    )
    return HttpResponse("", status=202)


def handle_send_ack_report_computed_task(client_message: message.tasks.AckReportComputedTask) -> HttpResponse:
    task_to_compute = client_message.report_computed_task.task_to_compute
    report_computed_task = client_message.report_computed_task
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)

    validate_task_to_compute(task_to_compute)
    validate_that_golem_messages_are_signed_with_key(
        provider_public_key,
        report_computed_task,
        task_to_compute.want_to_compute_task
    )
    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        task_to_compute,
    )

    if get_current_utc_timestamp() <= task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
        with transaction.atomic(using='control'):
            try:
                subtask = Subtask.objects.select_for_update().get(
                    subtask_id=task_to_compute.compute_task_def['subtask_id'],
                )
            except Subtask.DoesNotExist:
                raise Http400(
                    "'ForceReportComputedTask' for this subtask_id has not been initiated yet. Can't accept your 'AckReportComputedTask'.",
                    error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED,
                )

            if subtask.state_enum != Subtask.SubtaskState.FORCING_REPORT:
                raise Http400(
                    f"Subtask state is {subtask.state} instead of FORCING_REPORT. Can't accept your 'AckReportComputedTask'.",
                    error_code=ErrorCode.QUEUE_WRONG_STATE,
                )

            if subtask.report_computed_task.subtask_id != task_to_compute.compute_task_def['subtask_id']:
                raise Http400(
                    "Received subtask_id does not match one in related ReportComputedTask. Can't accept your 'AckReportComputedTask'.",
                    error_code=ErrorCode.QUEUE_SUBTASK_ID_MISMATCH,
                )

            if subtask.requestor.public_key_bytes != requestor_public_key:
                raise Http400(
                    "Subtask requestor key does not match current client key. Can't accept your 'AckReportComputedTask'.",
                    error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH,
                )

            if subtask.ack_report_computed_task_id is not None or subtask.reject_report_computed_task_id is not None:
                raise Http400(
                    "Received AckReportComputedTask but RejectReportComputedTask "
                    "or another AckReportComputedTask for this task has already been submitted.",
                    error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST,
                )
            validate_all_messages_identical([
                task_to_compute,
                deserialize_message(subtask.task_to_compute.data.tobytes()),
            ])
            report_computed_task = substitute_new_report_computed_task_if_needed(
                report_computed_task_from_acknowledgement=report_computed_task,
                stored_report_computed_task=deserialize_message(subtask.report_computed_task.data.tobytes()),
            )

            subtask = update_and_return_updated_subtask(
                subtask=subtask,
                state=Subtask.SubtaskState.REPORTED,
                next_deadline=None,
                set_next_deadline=True,
                ack_report_computed_task=client_message,
                report_computed_task=report_computed_task,
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.ForceReportComputedTaskResponse,
                client_public_key=provider_public_key,
                queue=PendingResponse.Queue.Receive,
                subtask=subtask,
            )
            logging.log_message_added_to_queue(
                logger,
                client_message,
                requestor_public_key,
            )
            return HttpResponse("", status=202)
    else:
        logging.log_timeout(
            logger,
            client_message,
            requestor_public_key,
            task_to_compute.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
        )
        raise Http400(
            "Time to acknowledge this task is already over.",
            error_code=ErrorCode.QUEUE_TIMEOUT,
        )


def handle_send_reject_report_computed_task(client_message: message.tasks.RejectReportComputedTask) -> HttpResponse:

    validate_reject_report_computed_task(client_message)

    task_to_compute = client_message.task_to_compute
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)

    # If reason is GotMessageCannotComputeTask,
    # cannot_compute_task is instance of CannotComputeTask signed by the provider.
    if client_message.reason == message.tasks.RejectReportComputedTask.REASON.GotMessageCannotComputeTask:
        if not isinstance(client_message.cannot_compute_task, message.CannotComputeTask):
            raise Http400(
                "Expected CannotComputeTask inside RejectReportComputedTask.",
                error_code=ErrorCode.MESSAGE_INVALID,
            )
        validate_task_to_compute(client_message.cannot_compute_task.task_to_compute)
        validate_that_golem_messages_are_signed_with_key(
            provider_public_key,
            client_message.cannot_compute_task,
            task_to_compute.want_to_compute_task
        )

    # If reason is GotMessageTaskFailure,
    # task_failure is instance of TaskFailure signed by the provider.
    elif client_message.reason == message.tasks.RejectReportComputedTask.REASON.GotMessageTaskFailure:
        if not isinstance(client_message.task_failure, message.TaskFailure):
            raise Http400(
                "Expected TaskFailure inside RejectReportComputedTask.",
                error_code=ErrorCode.MESSAGE_INVALID,
            )
        validate_task_to_compute(client_message.task_failure.task_to_compute)
        validate_that_golem_messages_are_signed_with_key(
            provider_public_key,
            client_message.task_failure,
            task_to_compute.want_to_compute_task
        )

    # RejectReportComputedTask should contain empty cannot_compute_task and task_failure
    else:
        assert client_message.reason == message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded
        if client_message.cannot_compute_task is not None or client_message.task_failure is not None:
            raise Http400(
                "RejectReportComputedTask requires empty 'cannot_compute_task' and 'task_failure' with {} reason.".format(
                    client_message.reason.name
                ),
                error_code=ErrorCode.MESSAGE_INVALID,
            )
    with transaction.atomic(using='control'):
        try:
            subtask = Subtask.objects.select_for_update().get(
                subtask_id=task_to_compute.compute_task_def['subtask_id'],
            )
        except Subtask.DoesNotExist:
            raise Http400(
                "'ForceReportComputedTask' for this task and client combination has not been initiated yet. Can't accept your 'RejectReportComputedTask'.",
                error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED,
            )

        if subtask.state_enum != Subtask.SubtaskState.FORCING_REPORT:
            raise Http400(
                "Subtask state is {} instead of FORCING_REPORT. Can't accept your 'RejectReportComputedTask'.".format(
                    subtask.state
                ),
                error_code=ErrorCode.QUEUE_WRONG_STATE,
            )

        if subtask.report_computed_task.subtask_id != task_to_compute.compute_task_def['subtask_id']:
            raise Http400(
                "Received subtask_id does not match one in related ReportComputedTask. Can't accept your 'RejectReportComputedTask'.",
                error_code=ErrorCode.QUEUE_SUBTASK_ID_MISMATCH,
            )

        if subtask.requestor.public_key_bytes != requestor_public_key:
            raise Http400(
                "Subtask requestor key does not match current client key. Can't accept your 'RejectReportComputedTask'.",
                error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH,
            )

        validate_all_messages_identical(
            [
                task_to_compute,
                deserialize_message(subtask.task_to_compute.data.tobytes()),
            ]
        )

        if client_message.reason == message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded:
            subtask = update_and_return_updated_subtask(
                subtask=subtask,
                state=Subtask.SubtaskState.REPORTED,
                next_deadline=None,
                set_next_deadline=True,
                reject_report_computed_task=client_message,
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.ForceReportComputedTaskResponse,
                client_public_key=provider_public_key,
                queue=PendingResponse.Queue.Receive,
                subtask=subtask,
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.VerdictReportComputedTask,
                client_public_key=subtask.requestor.public_key_bytes,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                subtask=subtask,
            )
            logging.log_message_added_to_queue(
                logger,
                client_message,
                requestor_public_key,
            )
            return HttpResponse("", status=202)

        deserialized_message = deserialize_message(subtask.task_to_compute.data.tobytes())

        if get_current_utc_timestamp() <= deserialized_message.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME:
            if subtask.ack_report_computed_task_id is not None or subtask.ack_report_computed_task_id is not None:
                raise Http400(
                    "Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.",
                    error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST,
                )

            subtask = update_and_return_updated_subtask(
                subtask=subtask,
                state=Subtask.SubtaskState.FAILED,
                next_deadline=None,
                set_next_deadline=True,
                reject_report_computed_task=client_message,
            )
            store_pending_message(
                response_type=PendingResponse.ResponseType.ForceReportComputedTaskResponse,
                client_public_key=provider_public_key,
                queue=PendingResponse.Queue.Receive,
                subtask=subtask,
            )
            logging.log_message_added_to_queue(
                logger,
                client_message,
                requestor_public_key,
            )
            return HttpResponse("", status=202)
        else:
            logging.log_timeout(
                logger,
                client_message,
                requestor_public_key,
                deserialized_message.compute_task_def['deadline'] + settings.CONCENT_MESSAGING_TIME,
            )
            raise Http400(
                "Time to acknowledge this task is already over.",
                error_code=ErrorCode.QUEUE_TIMEOUT,
            )


def handle_send_force_get_task_result(
    client_message: ForceGetTaskResult
) -> Union[ForceGetTaskResultRejected, AckForceGetTaskResult, ServiceRefused]:
    task_to_compute = client_message.report_computed_task.task_to_compute
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)

    validate_that_golem_messages_are_signed_with_key(
        provider_public_key,
        client_message.report_computed_task,
        task_to_compute.want_to_compute_task
    )
    validate_task_to_compute(task_to_compute)
    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        task_to_compute,
    )

    maximum_download_time = calculate_maximum_download_time(
        client_message.report_computed_task.size,
        settings.MINIMUM_UPLOAD_RATE,
    )
    force_get_task_result_deadline = (
        client_message.report_computed_task.task_to_compute.compute_task_def['deadline'] +
        2 * settings.CONCENT_MESSAGING_TIME +
        maximum_download_time
    )

    if not get_current_utc_timestamp() <= force_get_task_result_deadline:
        logging.log_timeout(
            logger,
            client_message,
            requestor_public_key,
            force_get_task_result_deadline,
        )
        return message.concents.ForceGetTaskResultRejected(
            reason=message.concents.ForceGetTaskResultRejected.REASON.AcceptanceTimeLimitExceeded,
            force_get_task_result=client_message,
        )
    with transaction.atomic(using='control'):
        subtask = get_one_or_none(
            Subtask.objects.select_for_update(),
            subtask_id=task_to_compute.compute_task_def['subtask_id'],
        )
        if subtask is None:
            subtask = store_subtask(
                task_id=task_to_compute.compute_task_def['task_id'],
                subtask_id=task_to_compute.compute_task_def['subtask_id'],
                provider_public_key=provider_public_key,
                requestor_public_key=requestor_public_key,
                state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
                next_deadline=(
                        int(task_to_compute.compute_task_def['deadline']) +
                        2 * maximum_download_time +
                        3 * settings.CONCENT_MESSAGING_TIME
                ),
                task_to_compute=task_to_compute,
                report_computed_task=client_message.report_computed_task,
                force_get_task_result=client_message,
            )
        else:
            if not is_state_transition_possible(
                    to_=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
                    from_=subtask.state_enum,
            ):
                return message.concents.ServiceRefused(
                    reason=message.concents.ServiceRefused.REASON.DuplicateRequest,
                )
            if task_to_compute is not None and subtask.task_to_compute is not None:
                validate_all_messages_identical([
                    task_to_compute,
                    deserialize_message(subtask.task_to_compute.data.tobytes()),
                ])
            subtask = update_and_return_updated_subtask(
                subtask=subtask,
                state=Subtask.SubtaskState.FORCING_RESULT_TRANSFER,
                next_deadline=(
                        int(task_to_compute.compute_task_def['deadline']) +
                        2 * maximum_download_time +
                        3 * settings.CONCENT_MESSAGING_TIME
                ),
                set_next_deadline=True,
                task_to_compute=task_to_compute,
                report_computed_task=client_message.report_computed_task,
                force_get_task_result=client_message,
            )

        store_pending_message(
            response_type=PendingResponse.ResponseType.ForceGetTaskResultUpload,
            client_public_key=provider_public_key,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )

        result_transfer_request.delay(
            subtask.subtask_id,
            get_storage_result_file_path(
                subtask_id=subtask.subtask_id,
                task_id=subtask.task_id,
            ),
        )

        return message.concents.AckForceGetTaskResult(
            force_get_task_result = client_message,
        )


def handle_send_force_subtask_results(
    client_message: message.concents.ForceSubtaskResults
) -> Union[message.concents.ServiceRefused, message.concents.ForceSubtaskResultsRejected, HttpResponse]:
    report_computed_task = client_message.ack_report_computed_task.report_computed_task
    task_to_compute = report_computed_task.task_to_compute
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)

    validate_task_to_compute(task_to_compute)
    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        client_message.ack_report_computed_task,
        task_to_compute,
    )
    validate_that_golem_messages_are_signed_with_key(
        provider_public_key,
        report_computed_task,
        task_to_compute.want_to_compute_task
    )

    current_time = get_current_utc_timestamp()

    task_deadline = int(task_to_compute.compute_task_def['deadline'])
    subtask_verification_time = calculate_subtask_verification_time(report_computed_task)

    verification_deadline = task_deadline + subtask_verification_time
    forcing_acceptance_deadline = task_deadline + subtask_verification_time + settings.FORCE_ACCEPTANCE_TIME

    if forcing_acceptance_deadline < current_time:
        logging.log_timeout(
            logger,
            client_message,
            provider_public_key,
            forcing_acceptance_deadline,
        )
        return message.concents.ForceSubtaskResultsRejected(
            force_subtask_results=client_message,
            reason=message.concents.ForceSubtaskResultsRejected.REASON.RequestTooLate,
        )

    if current_time <= verification_deadline:
        logging.log_timeout(
            logger,
            client_message,
            provider_public_key,
            verification_deadline,
        )
        return message.concents.ForceSubtaskResultsRejected(
            force_subtask_results=client_message,
            reason=message.concents.ForceSubtaskResultsRejected.REASON.RequestPremature,
        )

    subtask = get_one_or_none(
        Subtask,
        subtask_id=task_to_compute.compute_task_def['subtask_id'],
    )

    if subtask is not None and not is_state_transition_possible(
        to_=Subtask.SubtaskState.FORCING_ACCEPTANCE,
        from_=subtask.state_enum,
    ):
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    (claim_against_requestor, claim_against_provider) = bankster.claim_deposit(
        subtask_id=task_to_compute.subtask_id,
        concent_use_case=ConcentUseCase.FORCED_ACCEPTANCE,
        requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
        provider_ethereum_address=task_to_compute.provider_ethereum_address,
        subtask_cost=task_to_compute.price,
        requestor_public_key=requestor_public_key,
        provider_public_key=provider_public_key,
    )

    assert claim_against_provider is None

    if claim_against_requestor is None:
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.TooSmallRequestorDeposit,
        )

    with transaction.atomic(using='control'):
        subtask = get_one_or_none(
            Subtask.objects.select_for_update(),
            subtask_id=task_to_compute.compute_task_def['subtask_id'],
        )

        if subtask is None:
            subtask = store_subtask(
                task_id=task_to_compute.compute_task_def['task_id'],
                subtask_id=task_to_compute.compute_task_def['subtask_id'],
                provider_public_key=provider_public_key,
                requestor_public_key=requestor_public_key,
                state=Subtask.SubtaskState.FORCING_ACCEPTANCE,
                next_deadline=forcing_acceptance_deadline + settings.CONCENT_MESSAGING_TIME,
                task_to_compute=client_message.ack_report_computed_task.report_computed_task.task_to_compute,
                report_computed_task=client_message.ack_report_computed_task.report_computed_task,
                ack_report_computed_task=client_message.ack_report_computed_task,
            )
        else:
            if task_to_compute is not None and subtask.task_to_compute is not None:
                validate_all_messages_identical([
                    task_to_compute,
                    deserialize_message(subtask.task_to_compute.data.tobytes()),
                ])
            subtask = update_and_return_updated_subtask(
                subtask=subtask,
                state=Subtask.SubtaskState.FORCING_ACCEPTANCE,
                next_deadline=forcing_acceptance_deadline + settings.CONCENT_MESSAGING_TIME,
                set_next_deadline=True,
                task_to_compute=client_message.ack_report_computed_task.report_computed_task.task_to_compute,
                report_computed_task=client_message.ack_report_computed_task.report_computed_task,
                ack_report_computed_task=client_message.ack_report_computed_task,
            )
        store_pending_message(
            response_type=PendingResponse.ResponseType.ForceSubtaskResults,
            client_public_key=requestor_public_key,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )
        logging.log_message_added_to_queue(
            logger,
            client_message,
            provider_public_key,
        )

        return HttpResponse("", status=202)


def handle_send_force_subtask_results_response(
    client_message: message.concents.ForceSubtaskResultsResponse
) -> HttpResponse:
    if client_message.subtask_results_accepted is not None and client_message.subtask_results_rejected is not None:
        raise Http400(
            f"ForceSubtaskResultsResponse contains both subtask_results_accepted and subtask_results_rejected",
            error_code=ErrorCode.MESSAGE_INVALID,
        )
    if client_message.subtask_results_accepted is None and client_message.subtask_results_rejected is None:
        raise Http400(
            f"ForceSubtaskResultsResponse does not contain any of subtask_results_accepted or subtask_results_rejected",
            error_code=ErrorCode.MESSAGE_INVALID,
        )
    task_to_compute = client_message.task_to_compute

    validate_task_to_compute(task_to_compute)
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)

    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        task_to_compute,
    )

    if isinstance(client_message.subtask_results_accepted, message.tasks.SubtaskResultsAccepted):
        subtask_results_accepted = client_message.subtask_results_accepted
        subtask_results_rejected = None
        state = Subtask.SubtaskState.ACCEPTED
        validate_that_golem_messages_are_signed_with_key(
            requestor_public_key,
            subtask_results_accepted,
        )
    else:
        task_to_compute = client_message.subtask_results_rejected.report_computed_task.task_to_compute
        subtask_results_accepted = None
        subtask_results_rejected = client_message.subtask_results_rejected
        state = Subtask.SubtaskState.REJECTED
        validate_that_golem_messages_are_signed_with_key(
            requestor_public_key,
            subtask_results_rejected,
        )
        validate_that_golem_messages_are_signed_with_key(
            provider_public_key,
            subtask_results_rejected.report_computed_task,
            task_to_compute.want_to_compute_task
        )
    with transaction.atomic(using='control'):
        try:
            subtask = Subtask.objects.select_for_update().get(
                subtask_id=task_to_compute.compute_task_def['subtask_id'],
            )
        except Subtask.DoesNotExist:
            raise Http400(
                f"ForceSubtaskResults for this subtask has not been initiated yet. Can't accept your {type(client_message).__name__}.",
                error_code=ErrorCode.QUEUE_COMMUNICATION_NOT_STARTED,
            )
        if subtask.subtask_results_accepted_id is not None or subtask.subtask_results_rejected_id is not None:
            raise Http400(
                "This subtask has been resolved already.",
                error_code=ErrorCode.SUBTASK_DUPLICATE_REQUEST,
            )

        if subtask.state_enum != Subtask.SubtaskState.FORCING_ACCEPTANCE:
            raise Http400(
                f"Subtask state is {subtask.state} instead of FORCING_ACCEPTANCE. Can't accept your '{type(client_message).__name__}'.",
                error_code=ErrorCode.QUEUE_WRONG_STATE,
            )

        if subtask.requestor.public_key_bytes != requestor_public_key:
            raise Http400(
                f"Subtask requestor key does not match current client key.  Can't accept your '{type(client_message).__name__}'.",
                error_code=ErrorCode.QUEUE_REQUESTOR_PUBLIC_KEY_MISMATCH,
            )

        validate_all_messages_identical([
            task_to_compute,
            deserialize_message(subtask.task_to_compute.data.tobytes()),
        ])

        delete_deposit_claim(
            subtask_id=task_to_compute.subtask_id,
            concent_use_case=ConcentUseCase.FORCED_ACCEPTANCE,
            ethereum_address=task_to_compute.provider_ethereum_address,
        )

        subtask = update_and_return_updated_subtask(
            subtask=subtask,
            state=state,
            next_deadline=None,
            set_next_deadline=True,
            subtask_results_accepted=subtask_results_accepted,
            subtask_results_rejected=subtask_results_rejected,
        )
        store_pending_message(
            response_type=(PendingResponse.ResponseType.ForceSubtaskResultsResponse),
            client_public_key=provider_public_key,
            queue=PendingResponse.Queue.Receive,
            subtask=subtask,
        )
        logging.log_message_added_to_queue(
            logger,
            client_message,
            requestor_public_key,
        )
        return HttpResponse("", status=202)


def get_clients_eth_accounts(task_to_compute: message.tasks.TaskToCompute) -> Tuple[str, str]:
    assert isinstance(task_to_compute, message.tasks.TaskToCompute)

    requestor_eth_address   = task_to_compute.requestor_ethereum_address
    provider_eth_address    = task_to_compute.provider_ethereum_address
    return (requestor_eth_address, provider_eth_address)


def handle_send_force_payment(
    client_message: message.concents.ForcePayment
) -> Union[ServiceRefused, ForcePaymentRejected, ForcePaymentCommitted]:

    # Concent should not accept payment requests in soft shutdown mode.
    if config.SOFT_SHUTDOWN_MODE is True:
        raise ConcentInSoftShutdownMode

    if not (
        are_keys_and_addresses_unique_in_message_subtask_results_accepted(client_message.subtask_results_accepted_list) and
        are_subtask_results_accepted_messages_signed_by_the_same_requestor(client_message.subtask_results_accepted_list)
    ):
        return message.concents.ServiceRefused(
            reason = message.concents.ServiceRefused.REASON.InvalidRequest
        )

    if not are_items_unique([subtask_results_accepted.subtask_id for subtask_results_accepted in client_message.subtask_results_accepted_list]):
        return message.concents.ServiceRefused(
            reason = message.concents.ServiceRefused.REASON.DuplicateRequest
        )

    for subtask_results_accepted in client_message.subtask_results_accepted_list:
        validate_task_to_compute(subtask_results_accepted.task_to_compute)

    if sum([subtask_results_accepted.task_to_compute.price
            for subtask_results_accepted in client_message.subtask_results_accepted_list]) == 0:
        return message.concents.ForcePaymentRejected(
            force_payment=client_message,
            reason=message.concents.ForcePaymentRejected.REASON.NoUnsettledTasksFound,
        )

    cut_off_time = get_current_utc_timestamp()

    # Any of the items from list of overdue acceptances
    # matches condition cut_off_time < payment_ts + PAYMENT_DUE_TIME
    if any(
        cut_off_time < subtask_results_accepted.payment_ts + settings.PAYMENT_DUE_TIME
        for subtask_results_accepted in client_message.subtask_results_accepted_list
    ):
        return message.concents.ForcePaymentRejected(
            force_payment=client_message,
            reason=message.concents.ForcePaymentRejected.REASON.TimestampError,
        )

    task_to_compute = client_message.subtask_results_accepted_list[0].task_to_compute
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)
    (requestor_eth_address, provider_eth_address) = get_clients_eth_accounts(task_to_compute)
    validate_ethereum_addresses(requestor_eth_address, provider_eth_address)
    requestor_ethereum_public_key = hex_to_bytes_convert(task_to_compute.requestor_ethereum_public_key)

    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        *client_message.subtask_results_accepted_list,
        *[subtask_results_accepted.task_to_compute for subtask_results_accepted in client_message.subtask_results_accepted_list],
    )

    try:
        claim_against_requestor = bankster.settle_overdue_acceptances(
            requestor_ethereum_address=requestor_eth_address,
            provider_ethereum_address=provider_eth_address,
            acceptances=client_message.subtask_results_accepted_list,
            requestor_public_key=requestor_public_key,
        )
    except BanksterTimestampError:
        return message.concents.ForcePaymentRejected(
            force_payment=client_message,
            reason=message.concents.ForcePaymentRejected.REASON.TimestampError,
        )

    # Concent defines time T2 (end time) equal to youngest payment_ts from passed SubtaskResultAccepted messages from
    # subtask_results_accepted_list.
    payment_ts = min(
        subtask_results_accepted.payment_ts for subtask_results_accepted in client_message.subtask_results_accepted_list
    )

    if claim_against_requestor is None:
        return message.concents.ForcePaymentRejected(
            force_payment=client_message,
            reason=message.concents.ForcePaymentRejected.REASON.NoUnsettledTasksFound,
        )
    else:
        provider_force_payment_commited = message.concents.ForcePaymentCommitted(
            payment_ts              = payment_ts,
            task_owner_key          = requestor_ethereum_public_key,
            provider_eth_account    = provider_eth_address,
            amount_paid             = claim_against_requestor.amount,
            amount_pending          = 0,
            recipient_type          = message.concents.ForcePaymentCommitted.Actor.Provider,
        )

        requestor_force_payment_commited = message.concents.ForcePaymentCommitted(
            payment_ts              = payment_ts,
            task_owner_key          = requestor_ethereum_public_key,
            provider_eth_account    = provider_eth_address,
            amount_paid             = claim_against_requestor.amount,
            amount_pending          = 0,
            recipient_type          = message.concents.ForcePaymentCommitted.Actor.Requestor,
        )

        with transaction.atomic(using='control'):
            store_pending_message(
                response_type=PendingResponse.ResponseType.ForcePaymentCommitted,
                client_public_key=requestor_public_key,
                queue=PendingResponse.Queue.ReceiveOutOfBand,
                payment_message=requestor_force_payment_commited
            )

        provider_force_payment_commited.sig = None
        return provider_force_payment_commited


def handle_unsupported_golem_messages_type(client_message: Any) -> None:
    if hasattr(client_message, 'header') and hasattr(client_message.header, 'type_'):
        raise Http400(
            f"This message type ({type(client_message).__name__}) is either not supported or cannot be submitted to Concent.",
            error_code=ErrorCode.MESSAGE_UNEXPECTED,
        )
    else:
        raise Http400(
            "Unknown message type or not a Golem message.",
            error_code=ErrorCode.MESSAGE_UNKNOWN,
        )


def store_subtask(
    task_id: str,
    subtask_id: str,
    provider_public_key: bytes,
    requestor_public_key: bytes,
    state: Subtask.SubtaskState,
    next_deadline: Optional[int],
    task_to_compute: message.TaskToCompute,
    report_computed_task: message.ReportComputedTask,
    ack_report_computed_task: Optional[message.tasks.AckReportComputedTask] = None,
    reject_report_computed_task: Optional[message.tasks.RejectReportComputedTask] = None,
    subtask_results_accepted: Optional[message.tasks.SubtaskResultsAccepted] = None,
    subtask_results_rejected: Optional[message.tasks.SubtaskResultsRejected] = None,
    force_get_task_result: Optional[message.concents.ForceGetTaskResult] = None,
) -> Subtask:
    """
    Validates and stores subtask and its data in Subtask table.
    Stores related messages in StoredMessage table and adds relation to newly created subtask.
    """
    assert isinstance(task_id,              str)
    assert isinstance(subtask_id,           str)
    assert isinstance(provider_public_key,  bytes)
    assert isinstance(requestor_public_key, bytes)
    assert isinstance(task_to_compute, message.TaskToCompute)
    assert isinstance(report_computed_task, message.ReportComputedTask)
    assert state in Subtask.SubtaskState
    assert (state in Subtask.ACTIVE_STATES)  == (isinstance(next_deadline, (int, float)))
    assert (state in Subtask.PASSIVE_STATES) == (next_deadline is None)
    try:
        provider = Client.objects.get_or_create_full_clean(provider_public_key)
        requestor = Client.objects.get_or_create_full_clean(requestor_public_key)
        computation_deadline = task_to_compute.compute_task_def['deadline']
        result_package_size = report_computed_task.size

        subtask = Subtask(
            task_id=task_id,
            subtask_id=subtask_id,
            provider=provider,
            requestor=requestor,
            result_package_size=result_package_size,
            state=state.name,
            next_deadline=parse_timestamp_to_utc_datetime(next_deadline) if next_deadline is not None else None,
            computation_deadline=parse_timestamp_to_utc_datetime(computation_deadline),
            task_to_compute=store_message(task_to_compute, task_id, subtask_id),
            want_to_compute_task=store_message(task_to_compute.want_to_compute_task, task_id, subtask_id),
            report_computed_task=store_message(report_computed_task, task_id, subtask_id),
        )

        set_subtask_messages(
            subtask,
            ack_report_computed_task=ack_report_computed_task,
            reject_report_computed_task=reject_report_computed_task,
            subtask_results_accepted=subtask_results_accepted,
            subtask_results_rejected=subtask_results_rejected,
            force_get_task_result=force_get_task_result,
        )

        subtask.full_clean()
        subtask.save()

        logging.log_subtask_stored(
            logger=logger,
            task_id=task_id,
            subtask_id=subtask_id,
            state=state.name,
            provider_public_key=provider_public_key,
            requestor_public_key=requestor_public_key,
            computation_deadline=computation_deadline,
            result_package_size=result_package_size,
            next_deadline=next_deadline,
        )

        return subtask
    except IntegrityError:
        log(
            logger,
            f'IntegrityError when tried to store subtask with id {subtask_id}. Task_id: {task_id}. '
            f'Provider public key: {convert_public_key_to_hex(provider_public_key)}. '
            f'Requestor public key: {convert_public_key_to_hex(requestor_public_key)}.'
        )
        raise CreateModelIntegrityError


def handle_messages_from_database(client_public_key: bytes) -> Union[message.Message, None]:
    assert client_public_key not in ['', None]
    encoded_client_public_key = b64encode(client_public_key)

    with transaction.atomic(using='control'):
        pending_response = PendingResponse.objects.select_for_update().filter(
            client__public_key=encoded_client_public_key,
            delivered=False,
        ).order_by('created_at').first()

        if pending_response is None:
            return None

        assert pending_response.response_type_enum in set(PendingResponse.ResponseType)

        if pending_response.response_type_enum != PendingResponse.ResponseType.ForcePaymentCommitted and not \
                is_protocol_version_compatible(
                    pending_response.subtask.task_to_compute.protocol_version
                ):
            log(logger,
                f'Wrong version of golem messages in stored messages.'
                f'Version stored in database is { pending_response.subtask.task_to_compute.protocol_version},'
                f'Concent version is {settings.GOLEM_MESSAGES_VERSION}.',
                subtask_id=pending_response.subtask.subtask_id,
                client_public_key=client_public_key,
                )
            return message.concents.ServiceRefused(reason=message.concents.ServiceRefused.REASON.UnsupportedProtocolVersion)

        if pending_response.response_type == PendingResponse.ResponseType.ForceReportComputedTask.name:  # pylint: disable=no-member
            report_computed_task = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
            response_to_client = message.concents.ForceReportComputedTask(
                report_computed_task=report_computed_task
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForceReportComputedTaskResponse.name:  # pylint: disable=no-member
            if pending_response.subtask.ack_report_computed_task is not None:
                ack_report_computed_task = deserialize_message(
                    pending_response.subtask.ack_report_computed_task.data.tobytes())
                response_to_client = message.concents.ForceReportComputedTaskResponse(
                    ack_report_computed_task=ack_report_computed_task,
                    reason=message.concents.ForceReportComputedTaskResponse.REASON.AckFromRequestor,
                )
                mark_message_as_delivered_and_log(pending_response, response_to_client)
                return response_to_client

            elif pending_response.subtask.reject_report_computed_task is not None:
                reject_report_computed_task = deserialize_message(
                    pending_response.subtask.reject_report_computed_task.data.tobytes())
                response_to_client = message.concents.ForceReportComputedTaskResponse(
                    reject_report_computed_task=reject_report_computed_task,
                    reason=message.concents.ForceReportComputedTaskResponse.REASON.RejectFromRequestor,
                )
                if reject_report_computed_task.reason == message.tasks.RejectReportComputedTask.REASON.SubtaskTimeLimitExceeded:
                    ack_report_computed_task = message.tasks.AckReportComputedTask(
                        report_computed_task=deserialize_message(
                            pending_response.subtask.report_computed_task.data.tobytes()),
                    )
                    sign_message(ack_report_computed_task, settings.CONCENT_PRIVATE_KEY)
                    response_to_client = message.concents.ForceReportComputedTaskResponse(
                        ack_report_computed_task=ack_report_computed_task,
                        reason=message.concents.ForceReportComputedTaskResponse.REASON.ConcentAck,
                    )
                mark_message_as_delivered_and_log(pending_response, response_to_client)
                return response_to_client
            else:
                ack_report_computed_task = message.tasks.AckReportComputedTask(
                    report_computed_task=deserialize_message(
                        pending_response.subtask.report_computed_task.data.tobytes()),
                )
                sign_message(ack_report_computed_task, settings.CONCENT_PRIVATE_KEY)
                response_to_client = message.concents.ForceReportComputedTaskResponse(
                    ack_report_computed_task=ack_report_computed_task,
                    reason=message.concents.ForceReportComputedTaskResponse.REASON.ConcentAck,
                )
                mark_message_as_delivered_and_log(pending_response, response_to_client)
                return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.VerdictReportComputedTask.name:  # pylint: disable=no-member
            ack_report_computed_task = message.tasks.AckReportComputedTask(
                report_computed_task=deserialize_message(pending_response.subtask.report_computed_task.data.tobytes()),
            )
            sign_message(ack_report_computed_task, settings.CONCENT_PRIVATE_KEY)
            report_computed_task     = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
            response_to_client = message.concents.VerdictReportComputedTask(
                ack_report_computed_task    = ack_report_computed_task,
                force_report_computed_task  = message.concents.ForceReportComputedTask(
                    report_computed_task = report_computed_task,
                ),
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultFailed.name:  # pylint: disable=no-member
            task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes())
            response_to_client = message.concents.ForceGetTaskResultFailed(
                task_to_compute = task_to_compute,
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultUpload.name:  # pylint: disable=no-member
            force_get_task_result = deserialize_message(pending_response.subtask.force_get_task_result.data.tobytes())
            file_transfer_token = create_file_transfer_token_for_golem_client(
                force_get_task_result.report_computed_task,
                client_public_key,
                FileTransferToken.Operation.upload,
            )

            response_to_client = message.concents.ForceGetTaskResultUpload(
                file_transfer_token=file_transfer_token,
                force_get_task_result=force_get_task_result,
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForceGetTaskResultDownload.name:  # pylint: disable=no-member
            force_get_task_result = deserialize_message(pending_response.subtask.force_get_task_result.data.tobytes())
            file_transfer_token  = create_file_transfer_token_for_golem_client(
                force_get_task_result.report_computed_task,
                client_public_key,
                FileTransferToken.Operation.download,
            )

            response_to_client = message.concents.ForceGetTaskResultDownload(
                file_transfer_token=file_transfer_token,
                force_get_task_result=force_get_task_result,
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForceSubtaskResults.name:  # pylint: disable=no-member
            ack_report_computed_task = deserialize_message(pending_response.subtask.ack_report_computed_task.data.tobytes())
            response_to_client = message.concents.ForceSubtaskResults(
                ack_report_computed_task = ack_report_computed_task
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.SubtaskResultsSettled.name:  # pylint: disable=no-member
            task_to_compute = deserialize_message(pending_response.subtask.task_to_compute.data.tobytes())
            response_to_client = message.concents.SubtaskResultsSettled(
                origin=message.concents.SubtaskResultsSettled.Origin.ResultsRejected,
                task_to_compute=task_to_compute,
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForceSubtaskResultsResponse.name:  # pylint: disable=no-member
            subtask_results_accepted = pending_response.subtask.subtask_results_accepted
            subtask_results_rejected = pending_response.subtask.subtask_results_rejected

            assert (subtask_results_rejected is None and subtask_results_accepted is not None) or \
                   (subtask_results_accepted is None and subtask_results_rejected is not None)

            if subtask_results_accepted is not None:
                response_to_client = message.concents.ForceSubtaskResultsResponse(
                    subtask_results_accepted=deserialize_message(subtask_results_accepted.data.tobytes()),
                )
            else:
                response_to_client = message.concents.ForceSubtaskResultsResponse(
                    subtask_results_rejected=deserialize_message(subtask_results_rejected.data.tobytes()),  # type: ignore
                )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.SubtaskResultsRejected.name:  # pylint: disable=no-member
            report_computed_task = deserialize_message(pending_response.subtask.report_computed_task.data.tobytes())
            response_to_client = message.tasks.SubtaskResultsRejected(
                reason=message.tasks.SubtaskResultsRejected.REASON.ConcentResourcesFailure,
                report_computed_task=report_computed_task
            )
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        elif pending_response.response_type == PendingResponse.ResponseType.ForcePaymentCommitted.name:  # pylint: disable=no-member
            payment_message = pending_response.payments.filter(
                pending_response__pk = pending_response.pk
            ).order_by('id').last()

            response_to_client = message.concents.ForcePaymentCommitted(
                payment_ts=parse_datetime_to_timestamp(payment_message.payment_ts),
                task_owner_key=payment_message.task_owner_key.tobytes(),
                provider_eth_account=payment_message.provider_eth_account,
                amount_paid=payment_message.amount_paid,
                amount_pending=payment_message.amount_pending,
            )
            if payment_message.recipient_type == PaymentInfo.RecipientType.Requestor.name:  # pylint: disable=no-member
                response_to_client.recipient_type = message.concents.ForcePaymentCommitted.Actor.Requestor
            elif payment_message.recipient_type == PaymentInfo.RecipientType.Provider.name:  # pylint: disable=no-member
                response_to_client.recipient_type = message.concents.ForcePaymentCommitted.Actor.Provider
            else:
                return None
            mark_message_as_delivered_and_log(pending_response, response_to_client)
            return response_to_client

        else:
            return None


def mark_message_as_delivered_and_log(undelivered_message: PendingResponse, log_message: message.Message) -> None:
    undelivered_message.delivered = True
    undelivered_message.full_clean()
    undelivered_message.save()

    logging.log_receive_message_from_database(
        logger,
        log_message,
        undelivered_message.client.public_key_bytes,
        undelivered_message.response_type,
        undelivered_message.queue
    )


def update_and_return_updated_subtask(
    subtask: Subtask,
    state: Subtask.SubtaskState,
    next_deadline: Optional[int] = None,
    set_next_deadline: Optional[bool] = False,
    task_to_compute: Optional[message.TaskToCompute] = None,
    report_computed_task: Optional[message.ReportComputedTask] = None,
    ack_report_computed_task: Optional[message.tasks.AckReportComputedTask] = None,
    reject_report_computed_task: Optional[message.tasks.RejectReportComputedTask] = None,
    subtask_results_accepted: Optional[message.tasks.SubtaskResultsAccepted] = None,
    subtask_results_rejected: Optional[message.tasks.SubtaskResultsRejected] = None,
    force_get_task_result: Optional[message.concents.ForceGetTaskResult] = None,
) -> Subtask:
    """
    Validates and updates subtask and its data.
    Stores related messages in StoredMessage table and adds relation to newly created subtask.
    """
    assert isinstance(subtask, Subtask)
    assert state in Subtask.SubtaskState
    assert (state in Subtask.ACTIVE_STATES)  == (next_deadline is not None)
    assert (state in Subtask.PASSIVE_STATES) == (next_deadline is None)

    next_deadline_datetime = parse_timestamp_to_utc_datetime(next_deadline) if next_deadline is not None else None

    set_subtask_messages(
        subtask,
        task_to_compute=task_to_compute,
        report_computed_task=report_computed_task,
        ack_report_computed_task=ack_report_computed_task,
        reject_report_computed_task=reject_report_computed_task,
        subtask_results_accepted=subtask_results_accepted,
        subtask_results_rejected=subtask_results_rejected,
        force_get_task_result=force_get_task_result
    )

    if set_next_deadline:
        subtask.next_deadline = next_deadline_datetime
    if report_computed_task is not None:
        subtask.result_package_size = report_computed_task.size
    subtask.state = state.name
    subtask.full_clean()
    subtask.save()

    logging.log_subtask_updated(
        logger,
        subtask.task_id,
        subtask.subtask_id,
        state.name,
        subtask.provider.public_key_bytes,
        subtask.requestor.public_key_bytes,
        next_deadline,
    )

    # Concent should send e-mail notification when the last active subtask switches to a passive state.
    if config.SOFT_SHUTDOWN_MODE is True and not Subtask.objects.filter(state__in=Subtask.ACTIVE_STATES).exists():  # pylint: disable=no-member
        mail_admins(
            subject = 'Concent soft shutdown complete',
            message = (
                "All subtasks tracked by this Concent instance are now in passive states.\n"
                "It's safe to turn off the control cluster.\n"
                "Note that there may still be downloads in progress on the storage cluster."
            )
        )

    return subtask


def set_subtask_messages(
    subtask: Subtask,
    task_to_compute: Optional[message.TaskToCompute] = None,
    report_computed_task: Optional[message.ReportComputedTask] = None,
    ack_report_computed_task: Optional[message.tasks.AckReportComputedTask] = None,
    reject_report_computed_task: Optional[message.tasks.RejectReportComputedTask] = None,
    subtask_results_accepted: Optional[message.tasks.SubtaskResultsAccepted] = None,
    subtask_results_rejected: Optional[message.tasks.SubtaskResultsRejected] = None,
    force_get_task_result: Optional[message.concents.ForceGetTaskResult] = None
) -> None:
    """
    Stores and adds relation of passed StoredMessages to given subtask.
    If the message name is not present in kwargs, it doesn't do anything with it.
    """
    subtask_messages_to_set = {
        'task_to_compute': task_to_compute,
        'report_computed_task': report_computed_task,
        'ack_report_computed_task': ack_report_computed_task,
        'reject_report_computed_task': reject_report_computed_task,
        'subtask_results_accepted': subtask_results_accepted,
        'subtask_results_rejected': subtask_results_rejected,
        'force_get_task_result': force_get_task_result
    }

    assert set(subtask_messages_to_set).issubset({f.name for f in Subtask._meta.get_fields()})
    assert set(subtask_messages_to_set).issubset(set(Subtask.MESSAGE_FOR_FIELD))

    for message_name, message_type in Subtask.MESSAGE_FOR_FIELD.items():
        message_to_store = subtask_messages_to_set.get(message_name)
        if (
            message_to_store is not None and
            (
                getattr(subtask, message_name) is None or
                message_to_store.__class__ in Subtask.MESSAGE_REPLACEMENT_FOR_STATE[subtask.state_enum]
            )
        ):
            assert isinstance(message_to_store, message_type)
            stored_message = store_message(
                message_to_store,
                subtask.task_id,
                subtask.subtask_id,
            )
            setattr(subtask, message_name, stored_message)
            logging.log_stored_message_added_to_subtask(
                logger,
                subtask.task_id,
                subtask.subtask_id,
                subtask.state,
                message_type,
                message_to_store.provider_id,
                message_to_store.requestor_id,
            )


def store_message(
    golem_message: message.base.Message,
    task_id: str,
    subtask_id: str,
) -> StoredMessage:
    assert golem_message.header.type_ in library

    message_timestamp = parse_timestamp_to_utc_datetime(golem_message.timestamp)
    stored_message = StoredMessage(
        type=golem_message.header.type_,
        timestamp=message_timestamp,
        data=copy(golem_message).serialize(),
        task_id=task_id,
        subtask_id=subtask_id,
        protocol_version=settings.GOLEM_MESSAGES_VERSION
    )
    stored_message.full_clean()
    stored_message.save()

    return stored_message


def handle_send_subtask_results_verify(
    subtask_results_verify: message.concents.SubtaskResultsVerify
) -> Union[message.concents.AckSubtaskResultsVerify, message.concents.ServiceRefused]:
    subtask_results_rejected = subtask_results_verify.subtask_results_rejected
    report_computed_task = subtask_results_rejected.report_computed_task
    task_to_compute = report_computed_task.task_to_compute
    compute_task_def = task_to_compute.compute_task_def
    requestor_public_key = hex_to_bytes_convert(task_to_compute.requestor_public_key)
    provider_public_key = hex_to_bytes_convert(task_to_compute.provider_public_key)
    validate_golem_message_subtask_results_rejected(subtask_results_rejected)
    validate_that_golem_messages_are_signed_with_key(
        requestor_public_key,
        task_to_compute,
    )
    validate_that_golem_messages_are_signed_with_key(
        provider_public_key,
        report_computed_task,
        task_to_compute.want_to_compute_task
    )

    if subtask_results_rejected.reason != SubtaskResultsRejected.REASON.VerificationNegative:
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.InvalidRequest,
        )

    verification_deadline = (
        subtask_results_rejected.timestamp +
        settings.ADDITIONAL_VERIFICATION_CALL_TIME +
        calculate_maximum_download_time(
            report_computed_task.size,
            settings.MINIMUM_UPLOAD_RATE,
        )
    )

    if verification_deadline < get_current_utc_timestamp():
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.InvalidRequest,
        )

    if not is_golem_message_signed_with_key(
        requestor_public_key,
        subtask_results_rejected,
    ):
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.InvalidRequest,
        )

    subtask = get_one_or_none(
        Subtask,
        subtask_id=compute_task_def['subtask_id'],
    )

    if subtask is not None and not is_state_transition_possible(
        to_=Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER,
        from_=subtask.state_enum
    ):
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.DuplicateRequest,
        )

    try:
        (claim_against_requestor, _) = bankster.claim_deposit(
            subtask_id=task_to_compute.subtask_id,
            concent_use_case=ConcentUseCase.ADDITIONAL_VERIFICATION,
            requestor_ethereum_address=task_to_compute.requestor_ethereum_address,
            provider_ethereum_address=task_to_compute.provider_ethereum_address,
            subtask_cost=task_to_compute.price,
            requestor_public_key=requestor_public_key,
            provider_public_key=provider_public_key,
        )
    except TooSmallProviderDeposit:
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.TooSmallProviderDeposit,
        )

    if claim_against_requestor is None:
        return message.concents.ServiceRefused(
            reason=message.concents.ServiceRefused.REASON.TooSmallRequestorDeposit,
        )

    with transaction.atomic(using='control'):
        subtask = get_one_or_none(
            Subtask.objects.select_for_update(),
            subtask_id=compute_task_def['subtask_id'],
        )

        if subtask is None:
            store_subtask(
                task_id=compute_task_def['task_id'],
                subtask_id=compute_task_def['subtask_id'],
                provider_public_key=provider_public_key,
                requestor_public_key=requestor_public_key,
                state=Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER,
                next_deadline=verification_deadline,
                task_to_compute=task_to_compute,
                report_computed_task=report_computed_task,
                subtask_results_rejected=subtask_results_rejected,
            )
        else:
            if task_to_compute is not None and subtask.task_to_compute is not None:
                validate_all_messages_identical([
                    task_to_compute,
                    deserialize_message(subtask.task_to_compute.data.tobytes()),
                ])

            update_and_return_updated_subtask(
                subtask=subtask,
                state=Subtask.SubtaskState.VERIFICATION_FILE_TRANSFER,
                next_deadline=verification_deadline,
                set_next_deadline=True,
                task_to_compute=task_to_compute,
                report_computed_task=report_computed_task,
                subtask_results_rejected=subtask_results_rejected,
            )

    blender_rendering_deadline = verification_deadline + calculate_concent_verification_time(task_to_compute)

    send_blender_verification_request(
        compute_task_def,
        blender_rendering_deadline,
    )

    ack_subtask_results_verify = message.concents.AckSubtaskResultsVerify(
        subtask_results_verify=subtask_results_verify,
        file_transfer_token=create_file_transfer_token_for_verification_use_case(
            subtask_results_verify,
            provider_public_key,
        ),
    )
    return ack_subtask_results_verify


def handle_message(client_message: message.Message) -> Union[message.Message, HttpResponse, None]:
    if isinstance(client_message, message.concents.ForceReportComputedTask):
        return handle_send_force_report_computed_task(client_message)

    elif isinstance(client_message, message.tasks.AckReportComputedTask):
        return handle_send_ack_report_computed_task(client_message)

    elif isinstance(client_message, message.tasks.RejectReportComputedTask):
        return handle_send_reject_report_computed_task(client_message)

    elif (
        isinstance(client_message, message.concents.ForceGetTaskResult) and
        client_message.report_computed_task is not None
    ):
        return handle_send_force_get_task_result(client_message)

    elif (
        isinstance(client_message, message.concents.ForceSubtaskResults) and
        client_message.ack_report_computed_task is not None
    ):
        return handle_send_force_subtask_results(client_message)

    elif (
        isinstance(client_message, message.concents.ForceSubtaskResultsResponse)
    ):
        return handle_send_force_subtask_results_response(client_message)

    elif isinstance(client_message, message.concents.ForcePayment):
        return handle_send_force_payment(client_message)

    elif isinstance(client_message, message.concents.SubtaskResultsVerify):
        return handle_send_subtask_results_verify(client_message)

    else:
        return handle_unsupported_golem_messages_type(client_message)


def are_items_unique(items: list) -> bool:
    return len(items) == len(set(items))
