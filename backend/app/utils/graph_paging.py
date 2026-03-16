"""Graphiti 图谱分页读取工具。

基于 Graphiti 的数据模型（EntityNode / EntityEdge）从 Neo4j 中分页获取
所有节点和边，替代旧的 Zep Cloud SDK 分页逻辑。

用法：
    from graphiti.graphiti_client import get_graphiti_client
    from app.utils.graph_paging import fetch_all_nodes, fetch_all_edges

    graphiti = await get_graphiti_client()
    nodes = await fetch_all_nodes(graphiti)
    edges = await fetch_all_edges(graphiti)
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode
from graphiti_core.edges import EntityEdge

logger = logging.getLogger('mirofish.graph_paging')

_DEFAULT_PAGE_SIZE = 100
_MAX_ITEMS = 2000


async def fetch_all_nodes(
    graphiti: Graphiti,
    group_id: Optional[str] = None,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_ITEMS,
) -> List[EntityNode]:
    """
    分页获取图谱所有实体节点。

    使用 EntityNode.get_by_group_ids 的 uuid_cursor 分页机制，
    最多返回 max_items 条。

    Args:
        graphiti: Graphiti 客户端实例
        group_id: 图分区 ID（可选，None 则获取所有）
        page_size: 每页大小
        max_items: 最大返回数量

    Returns:
        EntityNode 列表
    """
    all_nodes: List[EntityNode] = []
    cursor: Optional[str] = None
    group_ids = [group_id] if group_id else None
    page_num = 0

    while True:
        page_num += 1
        try:
            batch = await EntityNode.get_by_group_ids(
                graphiti.driver,
                group_ids=group_ids,
                limit=page_size,
                uuid_cursor=cursor,
            )
        except Exception as e:
            logger.error(f"获取节点第 {page_num} 页失败: {e}")
            break

        if not batch:
            break

        all_nodes.extend(batch)

        if len(all_nodes) >= max_items:
            all_nodes = all_nodes[:max_items]
            logger.warning(f"节点数量达到上限 ({max_items})，停止分页")
            break

        if len(batch) < page_size:
            break

        # 使用最后一个节点的 uuid 作为游标
        cursor = batch[-1].uuid
        if not cursor:
            logger.warning(f"节点缺少 uuid 字段，在 {len(all_nodes)} 个节点处停止分页")
            break

    logger.info(f"共获取 {len(all_nodes)} 个节点（{page_num} 页）")
    return all_nodes


async def fetch_all_edges(
    graphiti: Graphiti,
    group_id: Optional[str] = None,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_items: int = _MAX_ITEMS,
) -> List[EntityEdge]:
    """
    分页获取图谱所有关系边。

    使用 EntityEdge.get_by_group_ids 的 uuid_cursor 分页机制。

    Args:
        graphiti: Graphiti 客户端实例
        group_id: 图分区 ID（可选，None 则获取所有）
        page_size: 每页大小
        max_items: 最大返回数量

    Returns:
        EntityEdge 列表
    """
    all_edges: List[EntityEdge] = []
    cursor: Optional[str] = None
    group_ids = [group_id] if group_id else None
    page_num = 0

    while True:
        page_num += 1
        try:
            batch = await EntityEdge.get_by_group_ids(
                graphiti.driver,
                group_ids=group_ids,
                limit=page_size,
                uuid_cursor=cursor,
            )
        except Exception as e:
            logger.error(f"获取边第 {page_num} 页失败: {e}")
            break

        if not batch:
            break

        all_edges.extend(batch)

        if len(all_edges) >= max_items:
            all_edges = all_edges[:max_items]
            logger.warning(f"边数量达到上限 ({max_items})，停止分页")
            break

        if len(batch) < page_size:
            break

        cursor = batch[-1].uuid
        if not cursor:
            logger.warning(f"边缺少 uuid 字段，在 {len(all_edges)} 条边处停止分页")
            break

    logger.info(f"共获取 {len(all_edges)} 条边（{page_num} 页）")
    return all_edges


async def fetch_node_edges(
    graphiti: Graphiti,
    node_uuid: str,
) -> List[EntityEdge]:
    """
    获取指定节点的所有关联边。

    Args:
        graphiti: Graphiti 客户端实例
        node_uuid: 节点 UUID

    Returns:
        EntityEdge 列表
    """
    try:
        edges = await EntityEdge.get_by_node_uuid(graphiti.driver, node_uuid)
        logger.info(f"节点 {node_uuid[:8]}... 关联 {len(edges)} 条边")
        return edges
    except Exception as e:
        logger.warning(f"获取节点 {node_uuid[:8]}... 的边失败: {e}")
        return []
