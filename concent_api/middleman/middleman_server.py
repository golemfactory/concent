import asyncio
from asyncio.base_events import BaseEventLoop
import traceback
from collections import OrderedDict
from contextlib import suppress
from logging import getLogger
from typing import Iterable
from typing import List
from typing import Optional
from typing import Tuple
import signal

from middleman.constants import CONNECTION_COUNTER_LIMIT
from middleman.constants import DEFAULT_EXTERNAL_PORT
from middleman.constants import DEFAULT_INTERNAL_PORT
from middleman.constants import ERROR_ADDRESS_ALREADY_IN_USE
from middleman.constants import LOCALHOST_IP
from middleman.constants import PROCESSING_TIMEOUT
from middleman.asynchronous_operations import is_authenticated
from middleman.asynchronous_operations import request_consumer
from middleman.asynchronous_operations import request_producer
from middleman.asynchronous_operations import response_consumer
from middleman.asynchronous_operations import response_producer
from middleman.utils import QueuePool
from middleman_protocol.constants import MAXIMUM_FRAME_LENGTH

logger = getLogger(__name__)
crash_logger = getLogger('crash')


class MiddleMan:
    def __init__(
        self,
        bind_address: Optional[str]=None,
        internal_port: Optional[int]=None,
        external_port: Optional[int]=None,
        loop: Optional[BaseEventLoop]=None
    ) -> None:
        self._bind_address = bind_address if bind_address is not None else LOCALHOST_IP
        self._internal_port = internal_port if internal_port is not None else DEFAULT_INTERNAL_PORT
        self._external_port = external_port if external_port is not None else DEFAULT_EXTERNAL_PORT
        self._server_for_concent: Optional[BaseEventLoop] = None
        self._server_for_signing_service = None
        self._is_signing_service_connection_active = False
        self._loop = loop if loop is not None else asyncio.get_event_loop()
        self._connection_id = 0
        self._request_queue: asyncio.Queue = asyncio.Queue(loop=self._loop)
        self._response_queue_pool = QueuePool(loop=self._loop)
        self._message_tracker: OrderedDict = OrderedDict()
        self._ss_connection_candidates: List[Tuple[asyncio.Task, asyncio.StreamWriter]] = []

        # Handle shutdown signal.
        self._loop.add_signal_handler(signal.SIGTERM, self._terminate_connections)

    def run(self) -> None:
        """
        It is a wrapper layer over "main loop" which handles exceptions
        """
        try:
            self._run()
        except KeyboardInterrupt:
            # if CTRl-C is pressed before server starts, it will intercepted here (exception will not be reported to Sentry)
            logger.info("Ctrl-C has been pressed.")
            logger.info("Exiting.")
        except SystemExit:
            # system exit should be reraised (returned) to OS
            raise
        except Exception as exception:  # pylint: disable=broad-except
            # All other (unhandled) exceptions should be reported to Sentry via crash logger
            logger.exception(str(exception))
            crash_logger.error(
                f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
            )

    def _run(self) -> None:
        """
        Main functionality is implemented here - start of the server and waiting for and handling incoming connections
        """
        try:
            # start MiddleMan server
            logger.info("Starting MiddleMan")
            self._start_middleman()
        except OSError as exception:
            logger.error(
                f"Exception <OSError> occurred while starting MiddleMan server for Concent: {str(exception)}"
            )
            exit(ERROR_ADDRESS_ALREADY_IN_USE)
        try:
            # Serve requests until Ctrl+C is pressed
            logger.info(
                'MiddleMan is serving for Concent on {}'.format(
                    self._server_for_concent.sockets[0].getsockname()  # type: ignore
                )
            )
            logger.info(
                'MiddleMan is serving for Signing Service on {}'.format(
                    self._server_for_signing_service.sockets[0].getsockname()  # type: ignore
                )
            )
            self._run_forever()
        except KeyboardInterrupt:
            logger.info("Ctrl-C has been pressed.")
        # Close the server
        logger.info("Server is closing...")
        self._close_middleman()
        logger.info("Closed.")
        exit()

    def _run_forever(self) -> None:
        self._loop.run_forever()

    def _start_middleman(self) -> None:
        concent_server_coroutine = asyncio.start_server(
            self._handle_concent_connection,
            self._bind_address,
            self._internal_port,
            loop=self._loop,
            limit=MAXIMUM_FRAME_LENGTH
        )
        self._server_for_concent = self._loop.run_until_complete(concent_server_coroutine)
        service_server_coroutine = asyncio.start_server(
            self._handle_service_connection,
            self._bind_address,
            self._external_port,
            loop=self._loop,
            limit=MAXIMUM_FRAME_LENGTH
        )
        self._server_for_signing_service = self._loop.run_until_complete(service_server_coroutine)

    def _close_middleman(self) -> None:
        self._server_for_concent.close()  # type: ignore
        self._loop.run_until_complete(self._server_for_concent.wait_closed())  # type: ignore
        self._server_for_signing_service.close()  # type: ignore
        self._loop.run_until_complete(self._server_for_signing_service.wait_closed())  # type: ignore
        self._cancel_pending_tasks(asyncio.Task.all_tasks(), await_cancellation=True)
        self._loop.close()

    async def _handle_concent_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks = []
        response_queue: asyncio.Queue = asyncio.Queue(loop=self._loop)
        connection_id = self._connection_id = (self._connection_id + 1) % CONNECTION_COUNTER_LIMIT
        self._response_queue_pool[connection_id] = response_queue
        try:
            request_producer_task = self._loop.create_task(
                request_producer(self._request_queue, response_queue, reader, connection_id)
            )
            response_consumer_task = self._loop.create_task(
                response_consumer(response_queue, writer, connection_id)
            )
            tasks.append(request_producer_task)
            tasks.append(response_consumer_task)
            await request_producer_task  # 1. wait until producer task finishes (Concent will sent no more messages)
            await asyncio.sleep(PROCESSING_TIMEOUT)  # 2. give some time to process items already put to request queue
            await response_queue.join()  # 3. wait until items from response queue are processed (sent back to Concent)
            response_consumer_task.cancel()

        except asyncio.CancelledError:
            # CancelledError shall not be treated as crash and logged in Sentry
            raise

        except Exception as exception:  # pylint: disable=broad-except
            crash_logger.error(
                f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
            )
            raise

        finally:
            # regardless of exception's occurrence, all unfinished tasks should be cancelled
            # if exceptions occurs, producer task might need cancelling as well
            self._cancel_pending_tasks(tasks)
            # remove response queue from the pool
            removed_queue: Optional[asyncio.Queue] = self._response_queue_pool.pop(connection_id, None)
            if removed_queue is None:
                logger.warning(f"Response queue for connection ID: {connection_id} has been already removed")
            else:
                logger.info(f"Removing response queue for connection ID: {connection_id}.")

    async def _handle_service_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._is_signing_service_connection_active:
            writer.close()
        else:
            tasks: list = []
            try:
                successful = await self._authenticate_signing_service(reader, writer)
                if not successful:
                    writer.close()
                    return
                request_consumer_task = self._loop.create_task(
                    request_consumer(
                        self._request_queue,
                        self._response_queue_pool,
                        self._message_tracker,
                        writer
                    )
                )
                response_producer_task = self._loop.create_task(
                    response_producer(
                        self._response_queue_pool,
                        reader,
                        self._message_tracker
                    )
                )
                futures = [request_consumer_task, response_producer_task]
                tasks = futures[:]
                done_tasks, pending_tasks = await asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)
                for future in pending_tasks:
                    future.cancel()
                for future in done_tasks:
                    exception_from_task = future.exception()
                    if exception_from_task is not None:
                        raise exception_from_task

            except asyncio.CancelledError:
                # CancelledError shall not be treated as crash and logged in Sentry
                pass

            except Exception as exception:  # pylint: disable=broad-except
                crash_logger.error(
                    f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
                )
                raise

            finally:
                # cancel all tasks - if task is already done/cancelled it makes no harm
                self._cancel_pending_tasks(tasks)
                self._is_signing_service_connection_active = False

    def _terminate_connections(self) -> None:
        logger.info('SIGTERM received - closing connections and exiting.')
        self._loop.stop()

    def _cancel_pending_tasks(self, tasks: Iterable[asyncio.Task], await_cancellation: bool = False) -> None:
        for task in tasks:
            task.cancel()
            if await_cancellation:
                # Now we should await task to execute it's cancellation.
                # Cancelled task raises asyncio.CancelledError that we can suppress:
                with suppress(asyncio.CancelledError):
                    self._loop.run_until_complete(task)

    async def _authenticate_signing_service(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        logger.info("Signing Service candidate has connected, authenticating...")
        authentication_task = self._loop.create_task(is_authenticated(reader, writer))
        index = len(self._ss_connection_candidates)
        self._ss_connection_candidates.append((authentication_task, writer))

        await authentication_task
        self._ss_connection_candidates.pop(index)

        is_signing_service_authenticated = authentication_task.result()
        if is_signing_service_authenticated:
            logger.info("Authentication successful: Signing Service has connected.")
            self._is_signing_service_connection_active = True
            self._abort_ongoing_authentication()
        else:
            logger.info("Authentication unsuccessful, closing connection with candidate.")
        return is_signing_service_authenticated

    def _abort_ongoing_authentication(self) -> None:
        counter = 0
        length = len(self._ss_connection_candidates)
        for task, writer in self._ss_connection_candidates:
            logger.info(f"Canceling task {counter}/{length}...")
            task.cancel()
            writer.close()
            logger.info("Canceled!")
            counter += 1
        self._ss_connection_candidates.clear()
