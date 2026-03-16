"""
实体读取与过滤服务
从 Graphiti 图谱（Neo4j）中读取节点，筛选出符合预定义实体类型的节点

注：文件名保留 zep_entity_reader.py 以保持向后兼容的 import 路径，
    内部实现已完全替换为 Graphiti API。
"""

import asyncio
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode as GraphitiEntityNode
from graphiti_core.edges import EntityEdge as GraphitiEntityEdge

from ..config import Config
from ..utils.logger import get_logger
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges, fetch_node_edges

logger = get_logger('mirofish.zep_entity_reader')


@dataclass
class EntityNode:
    """实体节点数据结构"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # 相关的边信息
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # 相关的其他节点信息
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """获取实体类型（排除默认的Entity标签）"""
        for label in self.labels:
            if label not in ["Entity", "Node", "Episodic"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """过滤后的实体集合"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


def _run_async(coro):
    """在同步代码中运行异步协程的辅助函数"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # 如果已有事件循环在运行，创建新线程运行
        # 注意：新线程中的 asyncio.run 会创建新事件循环
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# 线程局部存储，用于标记当前是否在独立事件循环的线程中
import threading
_thread_local = threading.local()


class ZepEntityReader:
    """
    实体读取与过滤服务（Graphiti 实现）
    
    保留类名 ZepEntityReader 以保持向后兼容，
    内部使用 Graphiti + Neo4j 替代 Zep Cloud SDK。
    
    主要功能：
    1. 从图谱读取所有节点
    2. 筛选出符合预定义实体类型的节点
    3. 获取每个实体的相关边和关联节点信息
    """
    
    def __init__(self, api_key: Optional[str] = None):
        # api_key 参数保留以兼容旧代码，不再使用
        pass
    
    async def _get_client(self) -> Graphiti:
        """
        获取 Graphiti 客户端。
        
        始终创建新的轻量实例，因为 _run_async 中的 asyncio.run() 每次都会创建新的事件循环，
        旧的 Graphiti 客户端内部的 Neo4j driver 绑定在旧的事件循环上无法复用。
        使用轻量版跳过索引创建，减少开销。
        """
        from graphiti.graphiti_client import create_graphiti_client_lite
        return await create_graphiti_client_lite()
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        获取图谱的所有节点（分页获取）

        Args:
            graph_id: 图谱ID（即 group_id）

        Returns:
            节点列表
        """
        return _run_async(self._get_all_nodes_async(graph_id))
    
    async def _get_all_nodes_async(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取所有节点的异步实现"""
        logger.info(f"获取图谱 {graph_id} 的所有节点...")
        graphiti = await self._get_client()
        nodes = await fetch_all_nodes(graphiti, group_id=graph_id)
        
        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": node.uuid,
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"共获取 {len(nodes_data)} 个节点")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        获取图谱的所有边（分页获取）

        Args:
            graph_id: 图谱ID

        Returns:
            边列表
        """
        return _run_async(self._get_all_edges_async(graph_id))
    
    async def _get_all_edges_async(self, graph_id: str) -> List[Dict[str, Any]]:
        """获取所有边的异步实现"""
        logger.info(f"获取图谱 {graph_id} 的所有边...")
        graphiti = await self._get_client()
        edges = await fetch_all_edges(graphiti, group_id=graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": edge.uuid,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"共获取 {len(edges_data)} 条边")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        获取指定节点的所有相关边
        
        Args:
            node_uuid: 节点UUID
            
        Returns:
            边列表
        """
        return _run_async(self._get_node_edges_async(node_uuid))
    
    async def _get_node_edges_async(self, node_uuid: str) -> List[Dict[str, Any]]:
        """获取节点边的异步实现"""
        try:
            graphiti = await self._get_client()
            edges = await fetch_node_edges(graphiti, node_uuid)
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": edge.uuid,
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"获取节点 {node_uuid} 的边失败: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        筛选出符合预定义实体类型的节点
        
        筛选逻辑（按优先级）：
        1. 如果节点有自定义标签（除Entity/Node/Episodic外），用自定义标签作为实体类型
        2. 如果节点只有默认标签但有有效名字，也视为合法实体，类型标记为 "Entity"
        3. 只跳过没有名字的空节点
        
        Args:
            graph_id: 图谱ID
            defined_entity_types: 预定义的实体类型列表（可选）
            enrich_with_edges: 是否获取每个实体的相关边信息
            
        Returns:
            FilteredEntities: 过滤后的实体集合
        """
        logger.info(f"开始筛选图谱 {graph_id} 的实体...")
        
        # 获取所有节点
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # 获取所有边（用于后续关联查找）
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # 构建节点UUID到节点数据的映射
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # 筛选符合条件的实体
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            name = node.get("name", "").strip()
            
            # 跳过没有名字的空节点
            if not name:
                continue
            
            # 提取自定义标签（排除默认标签）
            custom_labels = [l for l in labels if l not in ["Entity", "Node", "Episodic"]]
            
            if custom_labels:
                # 有自定义标签，用自定义标签作为实体类型
                if defined_entity_types:
                    matching_labels = [l for l in custom_labels if l in defined_entity_types]
                    if not matching_labels:
                        continue
                    entity_type = matching_labels[0]
                else:
                    entity_type = custom_labels[0]
            else:
                # 没有自定义标签，但有 Entity 标签且有名字 → 视为合法实体
                if "Entity" not in labels:
                    continue
                # 如果指定了类型过滤且不包含 "Entity"，跳过
                if defined_entity_types and "Entity" not in defined_entity_types:
                    continue
                entity_type = "Entity"
            
            entity_types_found.add(entity_type)
            
            # 创建实体节点对象
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # 获取相关边和节点
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # 获取关联节点的基本信息
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, "
                   f"实体类型: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        获取单个实体及其完整上下文（边和关联节点）
        """
        return _run_async(self._get_entity_with_context_async(graph_id, entity_uuid))
    
    async def _get_entity_with_context_async(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """获取单个实体的异步实现"""
        try:
            graphiti = await self._get_client()
            node = await GraphitiEntityNode.get_by_uuid(graphiti.driver, entity_uuid)
            
            if not node:
                return None
            
            # 获取节点的边
            edges_data = await self._get_node_edges_async(entity_uuid)
            
            # 获取所有节点用于关联查找
            all_nodes = await self._get_all_nodes_async(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # 处理相关边和节点
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges_data:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # 获取关联节点信息
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=node.uuid,
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"获取实体 {entity_uuid} 失败: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        获取指定类型的所有实体
        
        Args:
            graph_id: 图谱ID
            entity_type: 实体类型
            enrich_with_edges: 是否获取相关边信息
            
        Returns:
            实体列表
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
