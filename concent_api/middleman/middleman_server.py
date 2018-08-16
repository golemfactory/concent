import asyncio
import traceback
from collections import OrderedDict
from logging import getLogger

import signal

from middleman.constants import CONNECTION_COUNTER_LIMIT, PROCESSING_TIMEOUT
from middleman.constants import DEFAULT_EXTERNAL_PORT
from middleman.constants import DEFAULT_INTERNAL_PORT
from middleman.constants import ERROR_ADDRESS_ALREADY_IN_USE
from middleman.constants import LOCALHOST_IP
from middleman.queue_operations import request_consumer
from middleman.queue_operations import request_producer
from middleman.queue_operations import response_consumer
from middleman.queue_operations import response_producer
from middleman.utils import QueuePool
from middleman_protocol.constants import MAXIMUM_FRAME_LENGTH

logger = getLogger(__name__)
crash_logger = getLogger('crash')


class MiddleMan:
    def __init__(self, bind_address=None, internal_port=None, external_port=None, loop=None):
        self._bind_address = bind_address if bind_address is not None else LOCALHOST_IP
        self._internal_port = internal_port if internal_port is not None else DEFAULT_INTERNAL_PORT
        self._external_port = external_port if external_port is not None else DEFAULT_EXTERNAL_PORT
        self._server_for_concent = None
        self._server_for_signing_service = None
        self._is_signing_service_connection_active = False
        self._loop = loop if loop is not None else asyncio.get_event_loop()
        self._connection_id = 0
        self._request_queue = asyncio.Queue(loop=self._loop)
        self._response_queue_pool = QueuePool(loop=self._loop)
        self._message_tracker = OrderedDict()

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
                    self._server_for_concent.sockets[0].getsockname()
                )
            )
            logger.info(
                'MiddleMan is serving for Signing Service on {}'.format(
                    self._server_for_signing_service.sockets[0].getsockname()
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
        self._server_for_concent.close()
        self._loop.run_until_complete(self._server_for_concent.wait_closed())
        self._server_for_signing_service.close()
        self._loop.run_until_complete(self._server_for_signing_service.wait_closed())
        self._loop.close()

    async def _handle_concent_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        tasks = []
        response_queue = asyncio.Queue(loop=self._loop)
        self._connection_id = (self._connection_id + 1) % CONNECTION_COUNTER_LIMIT
        self._response_queue_pool[self._connection_id] = response_queue
        try:
            request_producer_task = self._loop.create_task(
                request_producer(self._request_queue, response_queue, reader, self._connection_id)
            )
            response_consumer_task = self._loop.create_task(
                response_consumer(response_queue, writer, self._connection_id)
            )
            tasks.append(request_producer_task)
            tasks.append(response_consumer_task)
            await request_producer_task  # 1. wait until producer task finishes (Concent will sent no more messages)
            await asyncio.sleep(PROCESSING_TIMEOUT)  # 2. give some time to process items already put to request queue
            await response_queue.join()  # 3. wait until items from response queue are processed (sent back to Concent)
            response_consumer_task.cancel()

        except Exception as exception:  # pylint: disable=broad-except
            crash_logger.error(
                f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
            )
            raise

        finally:
            for task in tasks:  # regardless of exception's occurrence, all unfinished tasks should be cancelled
                task.cancel()   # if exceptions occurs, producer task might need cancelling as well
            removed_queue = self._response_queue_pool.pop(self._connection_id, None)  # remove response queue from the pool
            if removed_queue is None:
                logger.warning(f"Response queue for connection ID: {self._connection_id} has been already removed")
            else:
                logger.info(f"Removing response queue for connection ID: {self._connection_id}.")

    async def _handle_service_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._is_signing_service_connection_active:
            writer.close()
        else:
            self._is_signing_service_connection_active = True
            tasks = []
            try:
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
            except Exception as exception:  # pylint: disable=broad-except
                crash_logger.error(
                    f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
                )
                raise
            finally:
                for task in tasks:  # cancel all tasks - if task is already done/cancelled it makes no harm
                    task.cancel()
                self._is_signing_service_connection_active = False

    def _terminate_connections(self) -> None:
        logger.info('SIGTERM received - closing connections and exiting.')
        self._loop.stop()
