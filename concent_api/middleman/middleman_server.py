import asyncio
import traceback
from logging import getLogger

import signal

from django.conf import settings

from middleman_protocol.constants import MAXIMUM_FRAME_LENGTH
from middleman_protocol.exceptions import BrokenEscapingInFrameMiddlemanProtocolError
from middleman_protocol.exceptions import MiddlemanProtocolError
from middleman_protocol.message import AbstractFrame
from middleman_protocol.message import ErrorFrame
from middleman_protocol.stream_async import handle_frame_receive_async
from middleman_protocol.stream_async import map_exception_to_error_code
from middleman_protocol.stream_async import send_over_stream_async

from middleman.constants import DEFAULT_EXTERNAL_PORT
from middleman.constants import DEFAULT_INTERNAL_PORT
from middleman.constants import ERROR_ADDRESS_ALREADY_IN_USE
from middleman.constants import LOCALHOST_IP

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
        try:
            frame = await handle_frame_receive_async(reader, settings.CONCENT_PUBLIC_KEY)
            remote_address = writer.get_extra_info('peername')
            print("Received %r from %r" % (frame, remote_address))
            await self._respond_to_user(frame, writer)
        except (BrokenEscapingInFrameMiddlemanProtocolError, asyncio.LimitOverrunError, MiddlemanProtocolError) as exception:
            await self._send_immediate_error(writer, exception)
        except Exception as exception:  # pylint: disable=broad-except
            crash_logger.error(
                f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
            )
            raise

    async def _handle_service_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._is_signing_service_connection_active:
            writer.close()
        else:
            self._is_signing_service_connection_active = True
            try:
                frame = await handle_frame_receive_async(reader, settings.CONCENT_PUBLIC_KEY)
                remote_address = writer.get_extra_info('peername')
                print("Received %r from %r" % (frame, remote_address))
                await self._respond_to_user(frame, writer)
            except (BrokenEscapingInFrameMiddlemanProtocolError, asyncio.LimitOverrunError, MiddlemanProtocolError) as exception:
                await self._send_immediate_error(writer, exception)
            except Exception as exception:  # pylint: disable=broad-except
                crash_logger.error(
                    f"Exception occurred: {exception}, Traceback: {traceback.format_exc()}"
                )
                raise
            finally:
                self._is_signing_service_connection_active = False

    async def _respond_to_user(self, frame: AbstractFrame, writer: asyncio.StreamWriter) -> None:  # pylint: disable=no-self-use
        await send_over_stream_async(frame, writer, settings.CONCENT_PRIVATE_KEY)
        writer.close()

    def _terminate_connections(self) -> None:
        logger.info('SIGTERM received - closing connections and exiting.')
        self._loop.stop()

    async def _send_immediate_error(self, writer: asyncio.StreamWriter, exception: Exception):
        error_code = map_exception_to_error_code(exception)
        # TODO: update after this constant is added to MiddlemanProtocol
        error_frame = ErrorFrame(
            (error_code, str(exception)),
            0,
        )
        await self._respond_to_user(error_frame, writer)
