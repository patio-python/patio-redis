import asyncio
import os
import time
from functools import reduce
from typing import AsyncGenerator, Union, Any
import operator

import pytest
from patio import ThreadPoolExecutor, Registry, NullExecutor
from patio_redis import RedisBroker


rpc = Registry(project="test", strict=True)


@rpc('mul')
def mul(*args: Union[int, float]) -> Union[int, float]:
    return reduce(operator.mul, args)


@rpc('div')
def div(*args: Union[int, float]) -> Union[int, float]:
    return reduce(operator.truediv, args)


@rpc('sleeper')
def sleeper(interval: int) -> None:
    return time.sleep(interval)


@pytest.fixture
async def thread_executor() -> AsyncGenerator[Any, ThreadPoolExecutor]:
    async with ThreadPoolExecutor(rpc) as executor:
        yield executor


REDIS_URL = os.getenv('REDIS_URL', "redis://127.0.0.1:6379/")


async def test_simple(thread_executor: ThreadPoolExecutor):
    async with RedisBroker(
        thread_executor, url=REDIS_URL, max_connections=10
    ) as broker:
        assert await broker.call(mul, 1, 2, 3, 4, 5) == 120

        with pytest.raises(ZeroDivisionError):
            assert await broker.call(div, 1, 2, 3, 4, 0)

        with pytest.raises(asyncio.TimeoutError):
            assert await broker.call(sleeper, 2, timeout=1)


async def test_simple_split(thread_executor: ThreadPoolExecutor):
    async with RedisBroker(
        thread_executor, url=REDIS_URL, max_connections=10
    ):
        async with NullExecutor(
            Registry(project="test", strict=True)
        ) as executor:
            async with RedisBroker(
                executor, url=REDIS_URL, max_connections=10
            ) as producer:

                assert await producer.call('mul', 1, 2, 3, 4, 5) == 120

                with pytest.raises(ZeroDivisionError):
                    assert await producer.call('div', 1, 2, 3, 4, 0)

                with pytest.raises(asyncio.TimeoutError):
                    assert await producer.call('sleeper', 2, timeout=1)
