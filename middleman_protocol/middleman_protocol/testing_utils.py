from mock import MagicMock


def async_stream_actor_mock(*args, **kwargs):
    m = MagicMock(*args, **kwargs)

    async def mock_coro(*a, **kw):
        return m(*a, **kw)

    mock_coro.mock = m
    return mock_coro
