import calendar
import base64
import binascii
import datetime
import time

from django.conf import settings
from django.utils                   import timezone
from mypy.types import Optional
from mypy.types                     import Union
import requests

from golem_messages                 import message
from golem_messages.datastructures  import FrozenDict
from golem_messages.exceptions      import MessageError
from golem_messages.shortcuts import dump

from core.exceptions                import Http400
from common.constants                import ErrorCode


def is_base64(data: str) -> bool:
    """
    Checks if given data is properly base64-encoded data.

    :returns bool
    """
    try:
        base64.b64decode(data, validate=True)
        return True
    except binascii.Error:
        return False


def get_current_utc_timestamp() -> int:
    """
    Returns current timestamp as int.
    Returned timestamp is guaranteed to be in UTC on systems where epoch is January 1, 1970, 00:00:00 (UTC).

    """
    current_timestamp = int(timezone.now().timestamp())
    assert calendar.timegm(time.gmtime()) - current_timestamp <= 1
    return current_timestamp


def parse_datetime_to_timestamp(date_time: datetime.datetime) -> int:
    """
    Returns timestamp in UTC as int from given datetime.
    Returned timestamp is relative to UNIX epoch and should works the same on all operating systems.
    It works for both naive and timezone-aware datetime object. Naive datetime is interpreted as if it was in UTC.

    """
    if date_time.tzinfo is None:
        return int(date_time.replace(tzinfo = timezone.utc).timestamp())
    else:
        return int(date_time.astimezone(timezone.utc).timestamp())


def parse_timestamp_to_utc_datetime(timestamp: int) -> datetime.datetime:
    """
    Returns UTC datetime from given timestamp.
    """
    return datetime.datetime.fromtimestamp(timestamp, timezone.utc)


def get_field_from_message(golem_message: message.base.Message, field_name: str) -> Union[str, dict, message.base.Message]:
    """
    Returns field value with given field name nested inside given Golem Message or FrozenDict
    by checking recursively from top to bottom.

    Returns None if field is not available.
    """

    def check_task_id(golem_message):
        assert isinstance(golem_message, (message.base.Message, FrozenDict))
        if isinstance(golem_message, FrozenDict):
            if field_name in golem_message:
                return golem_message[field_name]
            else:
                return None
        elif hasattr(golem_message, field_name):
            return getattr(golem_message, field_name)
        for slot in golem_message.__slots__:
            if isinstance(getattr(golem_message, slot), (message.base.Message, FrozenDict)):
                task_id = check_task_id(getattr(golem_message, slot))
                if task_id is not None:
                    return task_id
        return None

    return check_task_id(golem_message)


def deserialize_message(raw_message_data):
    try:
        golem_message = message.Message.deserialize(
            raw_message_data,
            None,
            check_time = False
        )
        assert golem_message is not None
        return golem_message
    except MessageError as exception:
        raise Http400(
            "Unable to deserialize Golem Message: {}.".format(exception),
            error_code=ErrorCode.MESSAGE_UNABLE_TO_DESERIALIZE,
        )


def sign_message(golem_message, priv_key):
    assert isinstance(golem_message, message.Message)
    assert isinstance(priv_key, bytes) and len(priv_key) == 32
    assert golem_message.sig is None

    golem_message = golem_message.serialize(sign_as = priv_key)
    golem_message = deserialize_message(golem_message)
    return golem_message


def get_storage_file_path(category, subtask_id, task_id):
    assert subtask_id is not None and task_id is not None and category is not None
    return f'blender/{category}/{task_id}/{task_id}.{subtask_id}.zip'


def get_storage_result_file_path(subtask_id, task_id):
    return get_storage_file_path('result', subtask_id, task_id)


def get_storage_scene_file_path(subtask_id, task_id):
    return get_storage_file_path('scene', subtask_id, task_id)


def get_storage_source_file_path(subtask_id, task_id):
    return get_storage_file_path('source', subtask_id, task_id)


def join_messages(*messages):
    if len(messages) == 1:
        return messages[0]
    return ' '.join(m.strip() for m in messages if m not in ['', None])


def upload_file_to_storage_cluster(
    file_content: bytes,
    file_path: str,
    upload_token: message.concents.FileTransferToken,
    client_private_key: Optional[bytes] = None,
    client_public_key: Optional[bytes] = None,
    content_public_key: Optional[bytes] = None,
    storage_cluster_address: Optional[str] = None,
) -> requests.Response:
    dumped_upload_token = dump(upload_token, None, content_public_key if content_public_key is not None else settings.CONCENT_PUBLIC_KEY)
    base64_encoded_token = base64.b64encode(dumped_upload_token).decode()
    headers = {
        'Authorization': 'Golem ' + base64_encoded_token,
        'Concent-Auth': base64.b64encode(
            dump(
                message.concents.ClientAuthorization(
                    client_public_key=(
                        client_public_key if client_public_key is not None else settings.CONCENT_PUBLIC_KEY
                    ),
                ),
                client_private_key if client_private_key is not None else settings.CONCENT_PRIVATE_KEY,
                settings.CONCENT_PUBLIC_KEY
            ),
        ).decode(),
        'Concent-Upload-Path': file_path,
        'Content-Type': 'application/octet-stream'
    }
    return requests.post(
        f"{storage_cluster_address if storage_cluster_address is not None else settings.STORAGE_CLUSTER_ADDRESS}upload/",
        headers=headers,
        data=file_content,
        verify=False
    )
