import asyncio
import math
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from functools import cached_property
from random import getrandbits
from typing import (
    Any, AsyncContextManager, AsyncGenerator, Dict, Optional, Tuple, TypedDict,
    Union,
)

from patio import AbstractExecutor, TaskFunctionType
from patio.broker import AbstractBroker, TimeoutType
from patio.broker.serializer import (
    AbstractSerializer, RestrictedPickleSerializer,
)
from redis.asyncio import Redis, RedisError, Sentinel, StrictRedis


class RedisTask(TypedDict):
    method: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    reply_to: str


class AbstractRedisBroker(AbstractBroker, ABC):
    def __init__(
        self,
        executor: AbstractExecutor,
        serializer: AbstractSerializer = RestrictedPickleSerializer(),
        max_connections: int = 50,
        **redis_kwargs: Any
    ):
        super().__init__(executor)
        self.serializer = serializer
        self.semaphore = asyncio.Semaphore(max_connections)
        self._redis_kwargs = redis_kwargs
        self._redis_kwargs["max_connections"] = max_connections

    @abstractmethod
    def get_redis_connection(self) -> AsyncContextManager[Redis]:
        ...

    @cached_property
    def loop(self) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    async def _execute(self, task: RedisTask) -> None:
        async with self.get_redis_connection() as connection:
            if not await connection.delete(task["reply_to"]):
                # if task expired do not execute it
                return

            try:
                await connection.rpush(
                    task["reply_to"] + ":result",
                    self.serializer.pack(
                        await self.executor.execute(
                            task["method"],
                            *task["args"],
                            **task["kwargs"],
                        ),
                    ),
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                await connection.rpush(
                    task["reply_to"] + ":error",
                    self.serializer.pack(e),
                )

    async def _worker(self) -> None:
        methods = list(self.executor.registry)

        while True:
            try:
                async with self.get_redis_connection() as connection:
                    key, value = await connection.blpop(methods)
                await self._execute(self.serializer.unpack(value))
            except (OSError, ConnectionError, RedisError):
                await asyncio.sleep(0)
                continue

    @abstractmethod
    async def connect(self) -> None:
        ...

    async def setup(self) -> None:
        await self.connect()

        if not self.executor.registry:
            return

        for _ in range(self.executor.max_workers):
            self.create_task(self._worker())

    async def call(
        self,
        func: Union[str, TaskFunctionType],
        *args: Any,
        timeout: Optional[TimeoutType] = 86400,
        **kwargs: Any,
    ) -> Any:
        async with self.get_redis_connection() as connection:
            if not isinstance(func, str):
                func = self.executor.registry.get_name(func)

            reply_to = ".".join((
                self.executor.registry.project or "",
                str(uuid.UUID(int=getrandbits(128))),
            ))

            payload = self.serializer.pack(
                RedisTask(
                    method=func,
                    args=args,
                    kwargs=kwargs,
                    reply_to=reply_to,
                ),
            )

            if timeout is None:
                await connection.set(reply_to, 1)
            else:
                await connection.setex(reply_to, math.ceil(timeout), 1)

            await connection.rpush(func, payload)

            result = await connection.blpop(
                [reply_to + ":result", reply_to + ":error"],
                timeout=timeout,
            )

            if result is None:
                raise asyncio.TimeoutError()

            str_key: str = result[0].decode()
            py_value = self.serializer.unpack(result[1])

            if str_key.endswith(":result"):
                return py_value
            if str_key.endswith(":error"):
                raise py_value

    @abstractmethod
    async def close_connection(self) -> None:
        ...

    async def close(self) -> None:
        await super().close()
        await self.close_connection()


class RedisBroker(AbstractRedisBroker):
    def __init__(
        self,
        executor: AbstractExecutor,
        serializer: AbstractSerializer = RestrictedPickleSerializer(),
        max_connections: int = 50,
        **redis_kwargs: Any
    ):
        super().__init__(executor, serializer, max_connections, **redis_kwargs)
        self._redis: Optional[Redis] = None

    @asynccontextmanager
    async def get_redis_connection(self) -> AsyncGenerator[Redis, Any]:
        if self._redis is None:
            raise RuntimeError("Broker still not setting up")

        async with self.semaphore:
            yield self._redis

    async def connect(self) -> None:
        kwargs = dict(self._redis_kwargs)
        url = kwargs.pop("url", None)
        if url:
            self._redis = await StrictRedis.from_url(url, **kwargs)
            return
        self._redis = await StrictRedis(**self._redis_kwargs)

    async def close_connection(self) -> None:
        if self._redis is None:
            return
        await self._redis.close()


class RedisSentinelBroker(AbstractRedisBroker):
    def __init__(
        self, executor: AbstractExecutor,
        serializer: AbstractSerializer = RestrictedPickleSerializer(),
        max_connections: int = 50,
        **redis_kwargs: Any
    ):
        super().__init__(
            executor=executor,
            serializer=serializer,
            max_connections=max_connections,
            **redis_kwargs,
        )
        self.__sentinel: Optional[Sentinel] = None
        self._service_name = redis_kwargs.pop("service_name")
        self.__active_connection: Optional[Redis] = None

    @asynccontextmanager
    async def get_redis_connection(self) -> AsyncGenerator[Redis, Any]:
        if (
            self.__active_connection is not None and
            self.__active_connection.connection is not None
        ):
            async with self.semaphore:
                yield self.__active_connection

        if self.__sentinel is None:
            raise RuntimeError(
                f"{self.__class__.__name__} still not setting up",
            )

        async with self.semaphore:
            yield await self.__sentinel.master_for(self._service_name)

    async def connect(self) -> None:
        self.__sentinel = Sentinel(**self._redis_kwargs)

    async def close_connection(self) -> None:
        if self.__active_connection is None:
            return
        await self.__active_connection.close()


__all__ = (
    "AbstractRedisBroker",
    "RedisBroker",
    "RedisSentinelBroker",
)
