import asyncio
import re
from contextlib import asynccontextmanager
from ipaddress import ip_address
from secrets import compare_digest
from typing import Annotated

import sentry_sdk
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sentry_sdk.integrations.logging import LoggingIntegration

from hibiapi import __version__
from hibiapi.app.routes import router as ImplRouter
from hibiapi.utils.cache import cache
from hibiapi.utils.config import Config
from hibiapi.utils.exceptions import ClientSideException, RateLimitReachedException
from hibiapi.utils.log import logger
from hibiapi.utils.net import BaseNetClient
from hibiapi.utils.temp import TempFile

DESCRIPTION = (
    """
**A program that implements easy-to-use APIs for a variety of commonly used sites**

- *Documents*:
    - [Redoc](/docs) (Easier to read and more beautiful)
    - [Swagger UI](/docs/test) (Integrated interactive testing function)

Project: [mixmoe/HibiAPI](https://github.com/mixmoe/HibiAPI)

"""
    + Config["content"]["slogan"].as_str().strip()
).strip()


if Config["log"]["sentry"]["enabled"].as_bool():
    sentry_sdk.init(
        dsn=Config["log"]["sentry"]["dsn"].as_str(),
        send_default_pii=Config["log"]["sentry"]["pii"].as_bool(),
        integrations=[LoggingIntegration(level=None, event_level=None)],
        traces_sample_rate=Config["log"]["sentry"]["sample"].get(float),
    )
else:
    sentry_sdk.init()


class AuthorizationModel(BaseModel):
    username: str
    password: str


AUTHORIZATION_ENABLED = Config["authorization"]["enabled"].as_bool()
AUTHORIZATION_ALLOWED = Config["authorization"]["allowed"].get(list[AuthorizationModel])

security = HTTPBasic()


async def basic_authorization_depend(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
):
    # NOTE: We use `compare_digest` to avoid timing attacks.
    # Ref: https://fastapi.tiangolo.com/advanced/security/http-basic-auth/
    for allowed in AUTHORIZATION_ALLOWED:
        if compare_digest(credentials.username, allowed.username) and compare_digest(
            credentials.password, allowed.password
        ):
            return credentials.username, credentials.password
    raise ClientSideException(
        f"Invalid credentials for user {credentials.username!r}",
        status_code=401,
        headers={"WWW-Authenticate": "Basic"},
    )


RATE_LIMIT_ENABLED = Config["limit"]["enabled"].as_bool()
RATE_LIMIT_MAX = Config["limit"]["max"].as_number()
RATE_LIMIT_INTERVAL = Config["limit"]["interval"].as_number()


async def rate_limit_depend(request: Request):
    if not request.client:
        return

    try:
        client_ip = ip_address(request.client.host)
        client_ip_hex = client_ip.packed.hex()
        limit_key = f"rate_limit:IPv{client_ip.version}-{client_ip_hex:x}"
    except ValueError:
        limit_key = f"rate_limit:fallback-{request.client.host}"

    request_count = await cache.incr(limit_key)
    if request_count <= 1:
        await cache.expire(limit_key, timeout=RATE_LIMIT_INTERVAL)
    elif request_count > RATE_LIMIT_MAX:
        limit_remain: int = await cache.get_expire(limit_key)
        raise RateLimitReachedException(headers={"Retry-After": limit_remain})

    return


async def flush_sentry():
    client = sentry_sdk.Hub.current.client
    if client is not None:
        client.close()
    sentry_sdk.flush()
    logger.debug("Sentry client has been closed")


async def cleanup_clients():
    opened_clients = [
        client for client in BaseNetClient.clients if not client.is_closed
    ]
    if opened_clients:
        await asyncio.gather(
            *map(lambda client: client.aclose(), opened_clients),
            return_exceptions=True,
        )
    logger.debug(f"Cleaned <r>{len(opened_clients)}</r> unclosed HTTP clients")


@asynccontextmanager
async def fastapi_lifespan(app: FastAPI):
    yield
    await asyncio.gather(cleanup_clients(), flush_sentry())


app = FastAPI(
    title="HibiAPI",
    version=__version__,
    description=DESCRIPTION,
    docs_url="/docs/test",
    redoc_url="/docs",
    lifespan=fastapi_lifespan,
)
app.include_router(
    ImplRouter,
    prefix="/api",
    dependencies=(
        ([Depends(basic_authorization_depend)] if AUTHORIZATION_ENABLED else [])
        + ([Depends(rate_limit_depend)] if RATE_LIMIT_ENABLED else [])
    ),
)
app.mount("/temp", StaticFiles(directory=TempFile.path, check_dir=False))


@app.get("/", include_in_schema=False)
async def redirect():
    return Response(status_code=302, headers={"Location": "/docs"})


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    content = Config["content"]["robots"].as_str().strip()
    return Response(content, status_code=200)


@app.middleware("http")
async def redirect_workaround_middleware(request: Request, call_next):
    """Temporary redirection workaround for #12"""
    if matched := re.match(
        r"^/(qrcode|pixiv|netease|bilibili)/(\w*)$", request.url.path
    ):
        service, path = matched.groups()
        redirect_url = request.url.replace(path=f"/api/{service}/{path}")
        return RedirectResponse(redirect_url, status_code=301)
    return await call_next(request)
