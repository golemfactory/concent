from asyncio import sleep
from asyncio import StreamReader
from asyncio import StreamWriter

import assertpy
from mock import MagicMock
from mock import Mock
from golem_messages import ECCx


def assertpy_bytes_starts_with(data: bytes, starting_data: bytes):
    """
    Custom function which allows testing if given bytes start with other bytes using assertpy.
    """

    assert isinstance(data, bytes)
    assert isinstance(starting_data, bytes)

    assertpy.assert_that(
        str(data)[2:-1]
    ).starts_with(
        str(starting_data)[2:-1]
    )


def async_stream_actor_mock(*args, **kwargs):
    m = MagicMock(*args, **kwargs)

    async def mock_coro(*a, **kw):
        await sleep(0.0000001)
        return m(*a, **kw)

    mock_coro.mock = m
    return mock_coro


def prepare_mocked_reader(return_sequence):
    mocked_reader = Mock(spec_set=StreamReader)
    mocked_reader.readuntil = async_stream_actor_mock(return_value=return_sequence)
    return mocked_reader


def prepare_mocked_writer():
    mocked_writer = Mock(spec_set=StreamWriter)
    mocked_writer.drain = async_stream_actor_mock()
    return mocked_writer


def generate_ecc_key_pair():
    ecc = ECCx(None)
    return (ecc.raw_privkey, ecc.raw_pubkey)
