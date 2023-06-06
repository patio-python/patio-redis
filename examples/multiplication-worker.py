import asyncio
import operator
from functools import reduce

from patio import Registry, ThreadPoolExecutor

from patio_redis import RedisBroker


rpc = Registry(project="test", strict=True)


@rpc("mul")
def mul(*args):
    return reduce(operator.mul, args)


async def main():
    async with ThreadPoolExecutor(rpc, max_workers=16) as executor:
        async with RedisBroker(
            executor, url="redis://127.0.0.1:6379", max_connections=50,
        ) as broker:
            await broker.join()


if __name__ == "__main__":
    asyncio.run(main())
