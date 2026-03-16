"""
图谱构建服务
使用 Graphiti + Neo4j 构建知识图谱（替代原 Zep Cloud SDK）
"""

import os
import json
import uuid
import time
import asyncio
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode as GraphitiEntityNode, EpisodeType
from graphiti_core.edges import EntityEdge as GraphitiEntityEdge

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor


# ============== Monkey-patch: 修复 Neo4j 不支持 Map 属性值的问题 ==============
# Graphiti 的 bulk_utils.add_nodes_and_edges_bulk_tx 内部会将 node.attributes
# 和 edge.attributes 直接 update 到 entity_data dict，然后写入 Neo4j。
# 但 Neo4j 不允许属性值为 dict/list[dict] 类型（只能是基本类型或基本类型数组）。
# 当 LLM 提取的属性包含嵌套结构时就会报错：
#   "Property values can only be of primitive types or arrays thereof"
#
# 解决方案：patch add_nodes_and_edges_bulk_tx（属性展开发生的地方），
# 在 entity_data 构建完毕后、写入 Neo4j 前，将所有非基本类型的属性值序列化为 JSON 字符串。

_patch_logger = logging.getLogger('mirofish.patch')

def _flatten_neo4j_properties(data: dict) -> dict:
    """将 dict 中的非 Neo4j 基本类型值序列化为 JSON 字符串。
    
    Neo4j 只接受: bool, int, float, str, bytes, datetime, 以及这些类型的 list。
    dict 和 list[dict] 都需要序列化为 JSON 字符串。
    """
    for key, value in list(data.items()):
        if isinstance(value, dict):
            data[key] = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            data[key] = json.dumps(value, ensure_ascii=False)
    return data

try:
    from graphiti_core.utils import bulk_utils as _bulk_utils
    _original_add_nodes_and_edges_bulk_tx = _bulk_utils.add_nodes_and_edges_bulk_tx

    async def _patched_add_nodes_and_edges_bulk_tx(
        tx, episodic_nodes, episodic_edges, entity_nodes, entity_edges, embedder, driver
    ):
        """Patched version: 在写入 Neo4j 前对实体/边属性做扁平化处理。
        
        原函数内部会执行 entity_data.update(node.attributes or {})，
        将 attributes 中的字段展平到 entity_data 中。如果 attributes 包含
        嵌套 dict/list[dict]，就会产生 Neo4j Map 类型错误。
        
        我们在调用原函数前，预先将 attributes 中的复杂类型序列化为 JSON 字符串。
        """
        for node in entity_nodes:
            if node.attributes:
                node.attributes = _flatten_neo4j_properties(dict(node.attributes))
        for edge in entity_edges:
            if edge.attributes:
                edge.attributes = _flatten_neo4j_properties(dict(edge.attributes))

        return await _original_add_nodes_and_edges_bulk_tx(
            tx, episodic_nodes, episodic_edges, entity_nodes, entity_edges, embedder, driver
        )

    _bulk_utils.add_nodes_and_edges_bulk_tx = _patched_add_nodes_and_edges_bulk_tx
    _patch_logger.info("Successfully patched graphiti_core.utils.bulk_utils.add_nodes_and_edges_bulk_tx")
except Exception as e:
    _patch_logger.warning(f"Failed to patch bulk_utils: {e}")
# ============== Monkey-patch END ==============


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    图谱构建服务
    使用 Graphiti API 构建知识图谱
    """
    
    def __init__(self):
        self._graphiti: Optional[Graphiti] = None
        self.task_manager = TaskManager()
    
    async def _get_client(self) -> Graphiti:
        """获取 Graphiti 客户端（延迟初始化）"""
        if self._graphiti is None:
            from graphiti.graphiti_client import get_graphiti_client
            self._graphiti = await get_graphiti_client()
        return self._graphiti
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        异步构建图谱
        
        Args:
            text: 输入文本
            ontology: 本体定义（来自接口1的输出）
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小
            batch_size: 每批发送的块数量
            
        Returns:
            任务ID
        """
        # 创建任务
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # 在后台线程中执行构建
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """图谱构建工作线程"""
        # 在新线程中运行 asyncio 事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self._build_graph_async(
                    task_id, text, ontology, graph_name,
                    chunk_size, chunk_overlap, batch_size
                )
            )
        finally:
            loop.close()
    
    async def _build_graph_async(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """图谱构建异步实现"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="开始构建图谱..."
            )
            
            # 1. 创建图谱（生成 group_id）
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"图谱已创建: {graph_id}"
            )
            
            # 2. 从本体中提取实体和边类型（用于 add_episode 的 entity_types 参数）
            entity_types_dict, edge_types_dict = self._build_type_dicts(ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="本体类型已准备"
            )
            
            # 3. 文本分块
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"文本已分割为 {total_chunks} 个块"
            )
            
            # 4. 逐个 chunk 调用 add_episode
            from graphiti.graphiti_client import create_graphiti_client
            graphiti = await create_graphiti_client()
            
            try:
                failed_chunks = 0
                max_consecutive_failures = 5  # 连续失败超过此数则中止
                consecutive_failures = 0
                
                for i, chunk in enumerate(chunks):
                    batch_num = i + 1
                    progress = 20 + int((i + 1) / total_chunks * 70)  # 20-90%
                    
                    self.task_manager.update_task(
                        task_id,
                        progress=progress,
                        message=f"处理第 {batch_num}/{total_chunks} 个文本块... (失败: {failed_chunks})"
                    )
                    
                    try:
                        await graphiti.add_episode(
                            name=f"{graph_name}_chunk_{batch_num}",
                            episode_body=chunk,
                            source_description=f"MiroFish Graph: {graph_name}",
                            reference_time=datetime.now(),
                            source=EpisodeType.text,
                            group_id=graph_id,
                            entity_types=entity_types_dict if entity_types_dict else None,
                            edge_types=edge_types_dict if edge_types_dict else None,
                        )
                        consecutive_failures = 0  # 成功则重置连续失败计数
                    except Exception as e:
                        failed_chunks += 1
                        consecutive_failures += 1
                        import logging
                        logging.getLogger(__name__).warning(
                            f"[{task_id}] 块 {batch_num}/{total_chunks} 处理失败 "
                            f"(连续失败: {consecutive_failures}, 总失败: {failed_chunks}): "
                            f"{str(e)[:200]}"
                        )
                        self.task_manager.update_task(
                            task_id,
                            progress=progress,
                            message=f"块 {batch_num} 处理失败 (总失败: {failed_chunks}): {str(e)[:100]}"
                        )
                        
                        if consecutive_failures >= max_consecutive_failures:
                            import logging
                            logging.getLogger(__name__).error(
                                f"[{task_id}] 连续 {max_consecutive_failures} 个块处理失败，中止构建"
                            )
                            break
                        
                        # 失败后多等一会再继续
                        await asyncio.sleep(2)
                        continue
                    
                    # 避免请求过快
                    if i < total_chunks - 1:
                        await asyncio.sleep(0.5)
                
                # 5. 获取图谱信息
                self.task_manager.update_task(
                    task_id,
                    progress=90,
                    message="获取图谱信息..."
                )
                
                graph_info = await self._get_graph_info_with_client(graphiti, graph_id)
            finally:
                await graphiti.close()
            
            # 完成
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """
        创建图谱（生成 group_id）
        
        Graphiti 使用 group_id 隔离不同图谱的数据，
        替代 Zep 的 graph.create() API。
        """
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        return graph_id
    
    def _build_type_dicts(self, ontology: Dict[str, Any]):
        """
        从本体定义中构建 entity_types 和 edge_types 字典。
        
        Graphiti 的 add_episode 接受 Pydantic BaseModel 类型的字典。
        """
        from pydantic import BaseModel, Field, BeforeValidator
        from typing import Optional, Annotated
        
        def _coerce_to_str(v):
            """将 LLM 返回的非字符串值（如 bool、int）强制转为 str"""
            if v is None:
                return v
            return str(v)
        
        # 宽容的 Optional[str] 类型：接受任意值并转为字符串
        CoercedStr = Annotated[Optional[str], BeforeValidator(_coerce_to_str)]
        
        entity_types_dict = {}
        edge_types_dict = {}
        
        # 构建实体类型
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            
            # 动态创建 Pydantic 模型
            attrs = {}
            annotations = {}
            
            for attr_def in entity_def.get("attributes", []):
                attr_name = attr_def["name"]
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = CoercedStr
            
            attrs["__annotations__"] = annotations
            attrs["__doc__"] = description
            
            entity_class = type(name, (BaseModel,), attrs)
            entity_class.__doc__ = description
            entity_types_dict[name] = entity_class
        
        # 构建边类型
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")
            
            attrs = {}
            annotations = {}
            
            for attr_def in edge_def.get("attributes", []):
                attr_name = attr_def["name"]
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = CoercedStr
            
            attrs["__annotations__"] = annotations
            attrs["__doc__"] = description
            
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (BaseModel,), attrs)
            edge_class.__doc__ = description
            edge_types_dict[name] = edge_class
        
        return entity_types_dict, edge_types_dict
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        设置图谱本体（兼容层）
        
        Graphiti 不需要预先设置本体，类型定义在 add_episode 时传入。
        此方法保留以保持 API 兼容性。
        """
        # Graphiti 不需要预先设置 ontology，
        # entity_types 和 edge_types 在 add_episode 时按需传入
        pass
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
        ontology: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        分批添加文本到图谱（同步包装）
        返回所有 episode 的 uuid 列表
        
        注意：此方法会在独立事件循环中创建独立的 Graphiti 客户端，
        避免与主线程事件循环的 asyncio Future 冲突。
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._add_text_batches_async(graph_id, chunks, batch_size, progress_callback, ontology)
            )
        finally:
            loop.close()
    
    async def _add_text_batches_async(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
        ontology: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """分批添加文本到图谱（异步实现）"""
        # 在当前事件循环中创建独立客户端，避免跨 loop 冲突
        from graphiti.graphiti_client import create_graphiti_client
        graphiti = await create_graphiti_client()
        
        # 从本体构建类型字典（如果有）
        entity_types_dict = None
        edge_types_dict = None
        if ontology:
            entity_types_dict, edge_types_dict = self._build_type_dicts(ontology)
        
        try:
            episode_uuids = []
            total_chunks = len(chunks)
            failed_chunks = 0
            max_consecutive_failures = 5  # 连续失败超过此数则中止
            consecutive_failures = 0
            _logger = logging.getLogger('mirofish.build')
            
            for i, chunk in enumerate(chunks):
                batch_num = i + 1
                
                if progress_callback:
                    progress = (i + 1) / total_chunks
                    progress_callback(
                        f"处理第 {batch_num}/{total_chunks} 个文本块... (失败: {failed_chunks})",
                        progress
                    )
                
                try:
                    result = await graphiti.add_episode(
                        name=f"chunk_{batch_num}",
                        episode_body=chunk,
                        source_description="MiroFish Graph Data",
                        reference_time=datetime.now(),
                        source=EpisodeType.text,
                        group_id=graph_id,
                        entity_types=entity_types_dict if entity_types_dict else None,
                        edge_types=edge_types_dict if edge_types_dict else None,
                    )
                    
                    if result and hasattr(result, 'episode'):
                        episode_uuids.append(result.episode.uuid)
                    
                    consecutive_failures = 0  # 成功则重置
                    
                    # 避免请求过快
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    failed_chunks += 1
                    consecutive_failures += 1
                    _logger.warning(
                        f"块 {batch_num}/{total_chunks} 处理失败 "
                        f"(连续失败: {consecutive_failures}, 总失败: {failed_chunks}): "
                        f"{str(e)[:200]}"
                    )
                    if progress_callback:
                        progress_callback(
                            f"块 {batch_num} 失败 (总失败: {failed_chunks}): {str(e)[:80]}",
                            (i + 1) / total_chunks
                        )
                    
                    if consecutive_failures >= max_consecutive_failures:
                        _logger.error(
                            f"连续 {max_consecutive_failures} 个块处理失败，中止构建"
                        )
                        raise RuntimeError(
                            f"连续 {max_consecutive_failures} 个块处理失败，中止构建。"
                            f"最后错误: {str(e)[:200]}"
                        )
                    
                    # 失败后多等一会再继续
                    await asyncio.sleep(2)
                    continue
            
            if failed_chunks > 0:
                _logger.warning(f"图谱构建完成，共 {failed_chunks}/{total_chunks} 个块失败")
            
            return episode_uuids
        finally:
            await graphiti.close()
    
    async def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息（创建独立客户端）"""
        from graphiti.graphiti_client import create_graphiti_client
        graphiti = await create_graphiti_client()
        try:
            return await self._get_graph_info_with_client(graphiti, graph_id)
        finally:
            await graphiti.close()
    
    async def _get_graph_info_with_client(self, graphiti: Graphiti, graph_id: str) -> GraphInfo:
        """获取图谱信息（使用传入的客户端）"""
        
        nodes = await fetch_all_nodes(graphiti, group_id=graph_id)
        edges = await fetch_all_edges(graphiti, group_id=graph_id)

        # 统计实体类型
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node", "Episodic"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        获取完整图谱数据（同步包装）
        """
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._get_graph_data_async(graph_id))
        finally:
            loop.close()
    
    async def _get_graph_data_async(self, graph_id: str) -> Dict[str, Any]:
        """
        获取完整图谱数据（包含详细信息）
        """
        # 在当前事件循环中创建独立客户端
        from graphiti.graphiti_client import create_graphiti_client
        graphiti = await create_graphiti_client()
        
        try:
            nodes = await fetch_all_nodes(graphiti, group_id=graph_id)
            edges = await fetch_all_edges(graphiti, group_id=graph_id)

            # 创建节点映射用于获取节点名称
            node_map = {}
            for node in nodes:
                node_map[node.uuid] = node.name or ""
            
            nodes_data = []
            for node in nodes:
                created_at = node.created_at
                if created_at:
                    created_at = str(created_at)
                
                nodes_data.append({
                    "uuid": node.uuid,
                    "name": node.name,
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                    "attributes": node.attributes or {},
                    "created_at": created_at,
                })
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": edge.uuid,
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "fact_type": edge.name or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "source_node_name": node_map.get(edge.source_node_uuid, ""),
                    "target_node_name": node_map.get(edge.target_node_uuid, ""),
                    "attributes": edge.attributes or {},
                    "created_at": str(edge.created_at) if edge.created_at else None,
                    "valid_at": str(edge.valid_at) if edge.valid_at else None,
                    "invalid_at": str(edge.invalid_at) if edge.invalid_at else None,
                    "expired_at": str(edge.expired_at) if edge.expired_at else None,
                    "episodes": edge.episodes or [],
                })
            
            return {
                "graph_id": graph_id,
                "nodes": nodes_data,
                "edges": edges_data,
                "node_count": len(nodes_data),
                "edge_count": len(edges_data),
            }
        finally:
            await graphiti.close()
    
    def delete_graph(self, graph_id: str):
        """
        删除图谱（清除 group_id 下的所有数据）
        """
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._delete_graph_async(graph_id))
        finally:
            loop.close()
    
    async def _delete_graph_async(self, graph_id: str):
        """删除图谱异步实现"""
        from graphiti.graphiti_client import create_graphiti_client
        graphiti = await create_graphiti_client()
        
        try:
            # 使用 Cypher 批量删除该 group_id 下的所有数据
            delete_query = """
            MATCH (n {group_id: $group_id})
            DETACH DELETE n
            """
            await graphiti.driver.execute_query(
                delete_query,
                {"group_id": graph_id},
            )
        finally:
            await graphiti.close()
