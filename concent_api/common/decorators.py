from functools import wraps
from logging import getLogger
from typing import Any
from typing import Callable
from typing import Union
import traceback

from django.conf import settings
from django.db.transaction import Atomic
from django.db.transaction import get_connection
from django.utils.decorators import ContextDecorator

from common.exceptions import ConcentFeatureIsNotAvailable
from common.exceptions import ConcentPendingTransactionError
from common.logging import LoggingLevel
from common.logging import log

logger = getLogger(__name__)
crash_logger = getLogger('concent.crash')


def provides_concent_feature(concent_feature: str) -> Callable:
    """
    Decorator for declaring that given `concent_feature` is required to be in setting CONCENT_FEATURES
    for decorated view or celery task function.
    """
    def decorator(_function: Callable) -> Callable:
        assert callable(_function)

        @wraps(_function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if concent_feature not in settings.CONCENT_FEATURES:
                raise ConcentFeatureIsNotAvailable(
                    f'Concent feature `{concent_feature}` is not enabled. Function `{_function.__name__}` cannot be called in this configuration.'
                )
            return _function(*args, **kwargs)
        return wrapper
    return decorator


def log_task_errors(task: Callable) -> Callable:

    @wraps(task)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            return task(*args, **kwargs)
        except Exception as exception:
            log(
                crash_logger,
                f'Exception occurred while executing task {task.__name__}: {exception}, Traceback: {traceback.format_exc()}',
                subtask_id=kwargs['subtask_id'] if 'subtask_id' in kwargs else None,
                logging_level=LoggingLevel.ERROR)
            raise
    return wrapper


class non_nesting_atomic(ContextDecorator):
    """
    This class acts as either decorator or context manager.
    It discovers when the callable or code is being run in nested database transaction and raises exception.
    Otherwise it wraps callable or code in database transaction.
    """

    def __init__(self, using: Union[str, Callable], savepoint: bool = True) -> None:
        self.using = using
        self.atomic_context_decorator = Atomic(self.using, savepoint)

    def __enter__(self) -> None:
        if (
            settings.DETECT_NESTED_TRANSACTIONS and
            get_connection(self.using).in_atomic_block
        ):
            raise ConcentPendingTransactionError(
                'Creation of new transaction in the same database detected inside pending transaction.'
            )
        return self.atomic_context_decorator.__enter__()

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        return self.atomic_context_decorator.__exit__(*args, **kwargs)

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        def decorated(*args: Any, **kwargs: Any) -> None:
            with self:
                return func(*args, **kwargs)

        return decorated
