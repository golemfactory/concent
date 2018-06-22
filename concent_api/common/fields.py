import base64
import binascii
import enum

from django.core.exceptions import ValidationError
from django.db              import models


class Base64Field(models.TextField):
    """
    Base64 encoding field for storing bytes data in Django TextFields.

    Requires b64encoded string for provider_public_key and requestor_public_key fields.
    Requires bytes object for provider_public_key_bytes and requestor_public_key_bytes fields.

    Typically you would set only one of the above, and it will get translated to other type on the flight.
    """

    default_error_messages = {
        'not_base64': "'%(value)s' value must be a base64 encoded string.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.field_name = None

    def contribute_to_class(self, cls, name, private_only = False, virtual_only=models.fields.NOT_PROVIDED):
        if self.db_column is None:
            self.db_column = name
        self.field_name = name + '_bytes'
        super().contribute_to_class(cls, name, private_only = private_only, virtual_only = virtual_only)
        setattr(cls, self.field_name, property(self.get_data, self.set_data))

    def get_data(self, obj):
        return base64.b64decode(getattr(obj, self.name), validate = True)

    def set_data(self, obj, data):
        setattr(obj, self.name, base64.b64encode(data))

    def validate(self, value, model_instance):
        super().validate(value, model_instance)
        try:
            base64.b64decode(
                getattr(model_instance, self.name),
                validate = True
            )
        except binascii.Error:
            raise ValidationError(
                self.error_messages['not_base64'],
                params = {'value': value}
            )


@enum.unique
class ChoiceEnum(enum.Enum):
    """
    Subclass of native python Enum class which can be used in Django models.
    """

    @classmethod
    def choices(cls):
        return tuple((x.name, x.value) for x in cls)
