from typing import Annotated, Optional

from fastapi import Depends, File, Form
from loguru import logger

from hibiapi.api.sauce import (
    DeduplicateType,
    HostUrl,
    NetRequest,
    SauceConstants,
    SauceEndpoint,
    UploadFileIO,
)
from hibiapi.utils.routing import SlashRouter

if (not SauceConstants.API_KEY) or (not all(map(str.strip, SauceConstants.API_KEY))):
    logger.warning("Sauce API key not set, SauceNAO endpoint will be unavailable")
    SauceConstants.CONFIG["enabled"].set(False)

__mount__, __config__ = "sauce", SauceConstants.CONFIG
router = SlashRouter(tags=["SauceNAO"])

SauceAPIRoot = NetRequest()


async def request_client():
    async with SauceAPIRoot as client:
        yield SauceEndpoint(client)


@router.get("/")
async def sauce_url(
    endpoint: Annotated[SauceEndpoint, Depends(request_client)],
    url: HostUrl,
    size: int = 30,
    deduplicate: DeduplicateType = DeduplicateType.ALL,
    database: Optional[int] = None,
    enabled_mask: Optional[int] = None,
    disabled_mask: Optional[int] = None,
):
    """
    ## Name: `sauce_url`

    > 使用SauceNAO检索网络图片

    ---

    ### Required:

    - ***HostUrl*** **`url`**
        - Description: 图片URL

    ---

    ### Optional:
    - ***int*** `size` = `30`
        - Description: 搜索结果数目
    - ***DeduplicateType*** `deduplicate` = `DeduplicateType.ALL`
        - Description: 结果去重模式
    - ***Optional[int]*** `database` = `None`
        - Description: 检索的数据库ID, 999为全部检索
    - ***Optional[int]*** `enabled_mask` = `None`
        - Description: 启用的检索数据库
    - ***Optional[int]*** `disabled_mask` = `None`
        - Description: 禁用的检索数据库
    """
    return await endpoint.search(
        url=url,
        size=size,
        deduplicate=deduplicate,
        database=database,
        enabled_mask=enabled_mask,
        disabled_mask=disabled_mask,
    )


@router.post("/")
async def sauce_form(
    endpoint: Annotated[SauceEndpoint, Depends(request_client)],
    file: bytes = File(..., max_length=SauceConstants.IMAGE_MAXIMUM_SIZE),
    size: int = Form(30),
    deduplicate: Annotated[DeduplicateType, Form()] = DeduplicateType.ALL,
    database: Optional[int] = Form(None),
    enabled_mask: Optional[int] = Form(None),
    disabled_mask: Optional[int] = Form(None),
):
    """
    ## Name: `sauce_form`

    > 使用SauceNAO检索表单上传图片

    ---

    ### Required:
    - ***bytes*** `file`
        - Description: 上传的图片

    ---

    ### Optional:
    - ***int*** `size` = `30`
        - Description: 搜索结果数目
    - ***DeduplicateType*** `deduplicate` = `DeduplicateType.ALL`
        - Description: 结果去重模式
    - ***Optional[int]*** `database` = `None`
        - Description: 检索的数据库ID, 999为全部检索
    - ***Optional[int]*** `enabled_mask` = `None`
        - Description: 启用的检索数据库
    - ***Optional[int]*** `disabled_mask` = `None`
        - Description: 禁用的检索数据库

    """
    return await endpoint.search(
        file=UploadFileIO(file),
        size=size,
        deduplicate=deduplicate,
        database=database,
        disabled_mask=disabled_mask,
        enabled_mask=enabled_mask,
    )
