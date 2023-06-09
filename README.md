[![PyPI - License](https://img.shields.io/pypi/l/patio-redis)](https://pypi.org/project/patio-redis) [![Wheel](https://img.shields.io/pypi/wheel/patio-redis)](https://pypi.org/project/patio-redis) [![Mypy](http://www.mypy-lang.org/static/mypy_badge.svg)]() [![PyPI](https://img.shields.io/pypi/v/patio-redis)](https://pypi.org/project/patio-redis) [![PyPI](https://img.shields.io/pypi/pyversions/patio-redis)](https://pypi.org/project/patio-redis) [![Coverage Status](https://coveralls.io/repos/github/patio-python/patio-redis/badge.svg?branch=master)](https://coveralls.io/github/patio-python/patio-redis?branch=master) ![tox](https://github.com/patio-python/patio-redis/workflows/tests/badge.svg?branch=master)

PATIO Redis
===========

PATIO is an acronym for **P**ython **A**synchronous **T**ask for Async**IO**.

This package provides Redis broker implementation.

Example
-------

### Worker

```python
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

```

### Producer

```python
import asyncio

from patio import NullExecutor, Registry

from patio_redis import RedisBroker


rpc = Registry(project="test", strict=True)


async def main():
    async with NullExecutor(rpc) as executor:
        async with RedisBroker(
            executor, url="redis://127.0.0.1/", max_connections=50,
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
```
