import asyncio

from middleman_protocol.constants import ErrorCode
from middleman_protocol.constants import FRAME_SEPARATOR
from middleman_protocol.constants import MIDDLEMAN_EXCEPTION_TO_ERROR_CODE_MAP
from middleman_protocol.exceptions import MiddlemanProtocolError
from middleman_protocol.stream import append_frame_separator
from middleman_protocol.stream import escape_decode_raw_message
from middleman_protocol.stream import escape_encode_raw_message


async def handle_frame_receive_async(reader: asyncio.StreamReader) -> bytes:
    raw_data = await reader.readuntil(FRAME_SEPARATOR)
    index = raw_data.index(FRAME_SEPARATOR)
    raw_data_without_separator = raw_data[:index]
    return escape_decode_raw_message(raw_data_without_separator)



def map_exception_to_error_code(exception: MiddlemanProtocolError) -> ErrorCode:
    return MIDDLEMAN_EXCEPTION_TO_ERROR_CODE_MAP.get(exception, ErrorCode.Unknown)


async def send_over_stream_async(data: bytes, writer: asyncio.StreamWriter) -> None:
    writer.write(append_frame_separator(escape_encode_raw_message(data)))
    await writer.drain()
