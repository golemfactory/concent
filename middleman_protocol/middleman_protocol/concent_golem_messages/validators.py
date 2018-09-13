from typing import Optional

from golem_messages.exceptions import FieldError


def validate_bytes(field_name: str, value: bytes, maximum_allowed_length: Optional[int]=None) -> None:
    assert isinstance(field_name, str)
    assert isinstance(value, bytes)

    if not isinstance(value, bytes):
        raise FieldError(
            'Should be a bytes field',
            field=field_name,
            value=value,
        )

    if maximum_allowed_length is not None and maximum_allowed_length < len(value):
        raise FieldError(
            f'Maximum allowed length is {maximum_allowed_length} but value has length {len(value)}',
            field=field_name,
            value=value,
        )


def validate_maximum_int_length(field_name: str, value: int, maximum_allowed_length: int) -> None:
    assert isinstance(field_name, str)
    assert isinstance(value, int)
    assert isinstance(maximum_allowed_length, int)

    if maximum_allowed_length < len(str(value)):
        raise FieldError(
            f'Maximum allowed length is {maximum_allowed_length} but value has length {len(str(value))}',
            field=field_name,
            value=value,
        )
