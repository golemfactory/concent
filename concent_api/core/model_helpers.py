from typing import Any
from typing import Optional
from typing import Type
from typing import Union

from django.db import IntegrityError
from django.db.models import Model
from django.db.models import QuerySet
from django.db.models.base import ModelBase
from psycopg2 import errorcodes as pg_errorcodes


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
        model_object = model.objects.get_or_create_full_clean(
            **kwargs,
        )
    except IntegrityError as exception:
        if exception.pgcode == pg_errorcodes.UNIQUE_VIOLATION:
            model_object = model.objects.get_or_create_full_clean(
                **kwargs,
            )
        else:
            raise
    return model_object
