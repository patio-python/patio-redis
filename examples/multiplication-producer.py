import asyncio
from aiomisc import timeout
from patio import NullExecutor, Registry
from patio_redis import RedisBroker


rpc = Registry(project="test", strict=True)


@timeout(10)
async def main():
    async with NullExecutor(rpc) as executor:
        async with RedisBroker(
            executor, url="redis://127.0.0.1/", max_connections=50
        ) as broker:
            for i in range(50):
                print(
                    await asyncio.gather(
                        *[
                            broker.call("mul", i, j, timeout=1)
                            for j in range(200)
                        ]
                    ),
                )


if __name__ == "__main__":
    asyncio.run(main())
