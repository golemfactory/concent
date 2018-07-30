from golem_messages.exceptions import FieldError


def validate_bytes(field_name, value):
    if not isinstance(value, bytes):
        raise FieldError(
            "Should be a bytes field",
            field=field_name,
            value=value,
        )
