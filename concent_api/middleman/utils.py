from typing import Dict
from typing import Tuple

import asyncio

from logging import getLogger
from logging import Logger

from middleman.constants import ResponseQueueItem
from middleman.constants import STANDARD_ERROR_MESSAGE
from middleman.constants import WRONG_TYPE_ERROR_MESSAGE


class QueuePool(dict):
    def __init__(
        self,
        initial_data: Dict[int, asyncio.Queue] = None,
        loop: asyncio.BaseEventLoop = None,
        logger: Logger = None
    ) -> None:
        super().__init__({k: v for k, v in initial_data.items()} if initial_data is not None else {})
        self.logger = logger if logger is not None else getLogger()
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        for key, value in self.items():
            validate_connection_to_queue_mapping(key, value)

    def __setitem__(self, key: int, value: asyncio.Queue) -> None:
        validate_connection_to_queue_mapping(key, value)
        self._ensure_key_uniqueness(key)
        super().__setitem__(key, value)

    def _ensure_key_uniqueness(self, key: int) -> None:
        if key in self:
            raise KeyError(STANDARD_ERROR_MESSAGE)

    def update(self, mapping: Dict[int, asyncio.Queue], **kwargs) -> None:
        for key in mapping.keys():
            self._ensure_key_uniqueness(key)
        super().update(mapping, **kwargs)

    def pop(self, key: int, **kwargs) -> asyncio.Queue:
        value = super().pop(key, **kwargs)
        if value is not None:
            self.loop.run_until_complete(
                self._log_discarded_items_from_the_queue(key, value)
            )
        return value

    def popitem(self) -> Tuple[int, asyncio.Queue]:
        key, value = super().popitem()
        if value is not None:
            self.loop.run_until_complete(
                self._log_discarded_items_from_the_queue(key, value)
            )
        return key, value

    def __delitem__(self, key: int) -> None:
        if key in self:
            self.loop.run_until_complete(
                self._log_discarded_items_from_the_queue(key, self.__getitem__(key))
            )
        super().__delitem__(key)

    async def _log_discarded_items_from_the_queue(self, connection_id: int, queue: asyncio.Queue) -> None:
        while queue.qsize() > 0:
            item: ResponseQueueItem = await queue.get()  # log all info about not yet retrieved items
            self.logger.info(
                f"Dropped message: {type(item.message)}, "
                f"Concent request ID: {item.concent_request_id}, "
                f"connection ID: {connection_id}"
            )


def validate_connection_to_queue_mapping(key: int, value: asyncio.Queue) -> None:
    if not isinstance(value, asyncio.Queue):
        raise ValueError(WRONG_TYPE_ERROR_MESSAGE)
    if not isinstance(key, int):
        raise ValueError(WRONG_TYPE_ERROR_MESSAGE)