from typing import Any
from typing import Optional
from typing import Type
from typing import Union

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Model
from django.db.models import QuerySet
from django.db.models.base import ModelBase
from psycopg2 import errorcodes as pg_errorcodes
from common.decorators import non_nesting_atomic


def get_one_or_none(
    model_or_query_set: Union[Model, QuerySet],
    **conditions: Any
)-> Optional[Model]:
    if isinstance(model_or_query_set, ModelBase):
        instances = model_or_query_set.objects.filter(**conditions)
        assert len(instances) <= 1
        return None if len(instances) == 0 else instances[0]
    else:
        instances = model_or_query_set.filter(**conditions)
        assert len(instances) <= 1
        return None if len(instances) == 0 else instances[0]


def get_or_create_with_retry(model: Type[Model], **kwargs: Any) -> Model:
    try:
        with non_nesting_atomic(using='control'):
            model_object = model.objects.get_or_create_full_clean(
                **kwargs,
            )
    except IntegrityError as exception:
        if exception.__cause__.pgcode == pg_errorcodes.UNIQUE_VIOLATION:
            model_object = model.objects.get_or_create_full_clean(
                **kwargs,
            )
        else:
            raise
    except ValidationError:
        with non_nesting_atomic(using='control'):
            model_object = model.objects.get_or_create_full_clean(
                **kwargs,
            )
    return model_object
