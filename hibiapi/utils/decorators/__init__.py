from __future__ import annotations

import asyncio
from asyncio import sleep as async_sleep
from collections.abc import Awaitable, Iterable
from functools import partial, wraps
from inspect import iscoroutinefunction
from time import sleep as sync_sleep
from typing import Callable, Protocol, TypeVar, overload

from typing_extensions import ParamSpec

from hibiapi.utils.decorators.enum import enum_auto_doc as enum_auto_doc
from hibiapi.utils.decorators.timer import Callable_T, TimeIt
from hibiapi.utils.log import logger

Argument_T = ParamSpec("Argument_T")
Return_T = TypeVar("Return_T")


class RetryT(Protocol):
    @overload
    def __call__(self, function: Callable_T) -> Callable_T: ...

    @overload
    def __call__(
        self,
        *,
        retries: int = ...,
        delay: float = ...,
        exceptions: Iterable[type[Exception]] | None = ...,
    ) -> RetryT: ...

    def __call__(
        self,
        function: Callable | None = ...,
        *,
        retries: int = ...,
        delay: float = ...,
        exceptions: Iterable[type[Exception]] | None = ...,
    ) -> Callable | RetryT: ...


@overload
def Retry(function: Callable_T) -> Callable_T: ...


@overload
def Retry(
    *,
    retries: int = ...,
    delay: float = ...,
    exceptions: Iterable[type[Exception]] | None = ...,
) -> RetryT: ...


def Retry(
    function: Callable | None = None,
    *,
    retries: int = 3,
    delay: float = 0.1,
    exceptions: Iterable[type[Exception]] | None = None,
) -> Callable | RetryT:
    if function is None:
        return partial(
            Retry,
            retries=retries,
            delay=delay,
            exceptions=exceptions,
        )

    timed_func = TimeIt(function)
    allowed_exceptions: tuple[type[Exception], ...] = tuple(exceptions or [Exception])
    assert (retries >= 1) and (delay >= 0)

    @wraps(timed_func)
    def sync_wrapper(*args, **kwargs):
        error: Exception | None = None
        for retried in range(retries):
            try:
                return timed_func(*args, **kwargs)
            except Exception as exception:
                error = exception
                if not isinstance(exception, allowed_exceptions):
                    raise
                logger.opt().debug(
                    f"Retry of {timed_func=} trigged "
                    f"due to {exception=} raised ({retried=}/{retries=})"
                )
                sync_sleep(delay)
        assert isinstance(error, Exception)
        raise error

    @wraps(timed_func)
    async def async_wrapper(*args, **kwargs):
        error: Exception | None = None
        for retried in range(retries):
            try:
                return await timed_func(*args, **kwargs)
            except Exception as exception:
                error = exception
                if not isinstance(exception, allowed_exceptions):
                    raise
                logger.opt().debug(
                    f"Retry of {timed_func=} trigged "
                    f"due to {exception=} raised ({retried=}/{retries})"
                )
                await async_sleep(delay)
        assert isinstance(error, Exception)
        raise error

    return async_wrapper if iscoroutinefunction(function) else sync_wrapper


def ToAsync(
    function: Callable[Argument_T, Return_T],
) -> Callable[Argument_T, Awaitable[Return_T]]:
    @TimeIt
    @wraps(function)
    async def wrapper(*args: Argument_T.args, **kwargs: Argument_T.kwargs) -> Return_T:
        return await asyncio.get_running_loop().run_in_executor(
            None, lambda: function(*args, **kwargs)
        )

    return wrapper
