import calendar
import base64
import binascii
import datetime
import functools
import time

from django.utils                   import timezone

from golem_messages                 import cryptography
from golem_messages                 import message
from golem_messages.datastructures  import FrozenDict
from golem_messages.exceptions      import MessageError

from core.constants                 import MESSAGE_TASK_ID_MAX_LENGTH
from core.exceptions                import Http400


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


def decode_key(key: str) -> bytes:
    return base64.b64decode(key.encode('ascii'), validate = True)


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


def get_field_from_message(golem_message: message.base.Message, field_name: str) -> str:
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


def decode_client_public_key(request):
    assert 'HTTP_CONCENT_CLIENT_PUBLIC_KEY' in request.META
    return decode_key(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'])


def decode_other_party_public_key(request):
    if 'HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY' not in request.META:
        raise Http400('Missing Concent-Other-Party-Public-Key HTTP when expected.')
    try:
        return decode_key(request.META['HTTP_CONCENT_OTHER_PARTY_PUBLIC_KEY'])
    except binascii.Error:
        raise Http400('The value in the Concent-Other-Party-Public-Key HTTP is not a valid base64-encoded value.')


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
        raise Http400("Unable to deserialize Golem Message: {}.".format(exception))


def sign_message(golem_message, priv_key):
    assert isinstance(golem_message, message.Message)
    assert isinstance(priv_key, bytes) and len(priv_key) == 32
    assert golem_message.sig is None

    signature = functools.partial(cryptography.ecdsa_sign, priv_key)
    golem_message = golem_message.serialize(sign_func = signature)
    golem_message = deserialize_message(golem_message)
    return golem_message


def get_result_file_path(task_id, subtask_id):
    assert isinstance(task_id, str)
    assert isinstance(subtask_id, str)
    assert len(task_id) <= MESSAGE_TASK_ID_MAX_LENGTH
    assert len(subtask_id) <= MESSAGE_TASK_ID_MAX_LENGTH

    return 'blender/result/{}/{}.{}.zip'.format(task_id, task_id, subtask_id)


def get_source_file_path(task_id, subtask_id):
    assert isinstance(task_id, str)
    assert isinstance(subtask_id, str)
    assert len(task_id) <= MESSAGE_TASK_ID_MAX_LENGTH
    assert len(subtask_id) <= MESSAGE_TASK_ID_MAX_LENGTH

    return 'blender/source/{}/{}.{}.zip'.format(task_id, task_id, subtask_id)
