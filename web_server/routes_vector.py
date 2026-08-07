# 自动拆分自 web_server.py（路由域: vector）
import logging
# ruff: noqa: F821

logger = logging.getLogger(__name__)
from fastapi import APIRouter

from web_server.app import (
    vector_browser,
)

router = APIRouter()


@router.get("/api/vector/stats")
async def vector_stats() -> dict[str, Any]:
    """向量库各层统计。"""
    return vector_browser.layer_stats()


@router.get("/api/vector/layers/{scope:str}")
async def vector_layer(
    scope: str, sub_id: str = "", offset: int = 0, limit: int = 50
) -> dict[str, Any]:
    """浏览指定层的文档。"""
    return vector_browser.list_documents(scope, sub_id, offset, limit)


@router.get("/api/vector/search")
async def vector_search(q: str = "", top_k: int = 3) -> dict[str, Any]:
    """跨层搜索。"""
    results = vector_browser.search_all(q, top_k_per_layer=top_k) if q else []
    return {"query": q, "results": results, "total": len(results)}


@router.get("/api/vector/doc/{scope}/{sub_id}/{doc_id}")
async def vector_doc(scope: str, sub_id: str, doc_id: str) -> dict[str, Any]:
    """文档详情 + 相似文档。"""
    doc = vector_browser.get_document(scope, sub_id, doc_id)
    if doc is None:
        return {"found": False}
    similar = vector_browser.similar_to(doc_id, scope, sub_id)
    return {"found": True, "doc": doc, "similar": similar}
