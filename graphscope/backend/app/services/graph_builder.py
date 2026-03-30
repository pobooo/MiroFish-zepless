"""
图谱构建服务
使用 Graphiti + Neo4j 构建知识图谱
"""

import json
import uuid
import asyncio
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from pydantic import BaseModel, Field, BeforeValidator
from typing import Annotated


# ============== Monkey-patch: 修复 Neo4j 不支持 Map 属性值的问题 ==============
_patch_logger = logging.getLogger('graphscope.patch')


def _flatten_neo4j_properties(data: dict) -> dict:
    """将 dict 中的非 Neo4j 基本类型值序列化为 JSON 字符串。"""
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
        """Patched: 在写入 Neo4j 前对实体/边属性做扁平化处理。"""
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


logger = logging.getLogger(__name__)


@dataclass
class BuildTask:
    """图谱构建任务状态"""
    task_id: str
    status: str = "pending"  # pending, processing, completed, failed
    progress: int = 0
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# 全局任务存储（内存级，进程重启会丢失）
_tasks: Dict[str, BuildTask] = {}


def get_task(task_id: str) -> Optional[BuildTask]:
    return _tasks.get(task_id)


class GraphBuilderService:
    """图谱构建服务：使用 Graphiti API 构建知识图谱"""

    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "GraphScope Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> str:
        """
        异步构建图谱，返回任务 ID

        Args:
            text: 输入文本
            ontology: 本体定义
            graph_name: 图谱名称
            chunk_size: 文本块大小
            chunk_overlap: 块重叠大小

        Returns:
            任务 ID
        """
        task_id = f"build_{uuid.uuid4().hex[:12]}"
        task = BuildTask(task_id=task_id)
        _tasks[task_id] = task

        thread = threading.Thread(
            target=self._build_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap),
            daemon=True,
        )
        thread.start()

        return task_id

    def _build_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ):
        """图谱构建工作线程"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                self._build_async(task_id, text, ontology, graph_name, chunk_size, chunk_overlap)
            )
        finally:
            loop.close()

    async def _build_async(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ):
        """图谱构建异步实现"""
        task = _tasks[task_id]
        try:
            task.status = "processing"
            task.progress = 5
            task.message = "开始构建图谱..."

            # 1. 生成 group_id
            group_id = f"graphscope_{uuid.uuid4().hex[:16]}"
            task.progress = 10
            task.message = f"图谱已创建: {group_id}"

            # 2. 构建类型字典
            entity_types_dict, edge_types_dict = self._build_type_dicts(ontology)
            task.progress = 15
            task.message = "本体类型已准备"

            # 3. 文本分块
            from app.utils.file_parser import split_text_into_chunks
            chunks = split_text_into_chunks(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            task.progress = 20
            task.message = f"文本已分割为 {total_chunks} 个块"

            # 4. 创建 Graphiti 客户端
            from app.graphiti.graphiti_client import create_graphiti_client
            graphiti = await create_graphiti_client()

            try:
                failed_chunks = 0
                max_consecutive_failures = 5
                consecutive_failures = 0

                for i, chunk in enumerate(chunks):
                    batch_num = i + 1
                    progress = 20 + int((i + 1) / total_chunks * 70)

                    task.progress = progress
                    task.message = f"处理第 {batch_num}/{total_chunks} 个文本块... (失败: {failed_chunks})"

                    try:
                        await graphiti.add_episode(
                            name=f"{graph_name}_chunk_{batch_num}",
                            episode_body=chunk,
                            source_description=f"GraphScope: {graph_name}",
                            reference_time=datetime.now(),
                            source=EpisodeType.text,
                            group_id=group_id,
                            entity_types=entity_types_dict if entity_types_dict else None,
                            edge_types=edge_types_dict if edge_types_dict else None,
                        )
                        consecutive_failures = 0
                    except Exception as e:
                        failed_chunks += 1
                        consecutive_failures += 1
                        logger.warning(
                            f"[{task_id}] 块 {batch_num}/{total_chunks} 失败 "
                            f"(连续: {consecutive_failures}, 总: {failed_chunks}): "
                            f"{str(e)[:200]}"
                        )
                        task.message = f"块 {batch_num} 失败 (总失败: {failed_chunks}): {str(e)[:100]}"

                        if consecutive_failures >= max_consecutive_failures:
                            logger.error(f"[{task_id}] 连续 {max_consecutive_failures} 个块失败，中止构建")
                            break

                        await asyncio.sleep(2)
                        continue

                    if i < total_chunks - 1:
                        await asyncio.sleep(0.5)

                # 5. 统计结果
                task.progress = 95
                task.message = "统计图谱信息..."

                count_result = await self._count_graph(graphiti, group_id)

                # 保存项目元数据（名称）到 Neo4j
                await self._save_project_meta(graphiti, group_id, graph_name)

            finally:
                await graphiti.close()

            task.status = "completed"
            task.progress = 100
            task.message = "图谱构建完成"
            task.result = {
                "group_id": group_id,
                "graph_name": graph_name,
                "chunks_total": total_chunks,
                "chunks_failed": failed_chunks,
                **count_result,
            }

        except Exception as e:
            import traceback
            task.status = "failed"
            task.error = f"{str(e)}\n{traceback.format_exc()}"
            task.message = f"构建失败: {str(e)[:200]}"

    async def _count_graph(self, graphiti: Graphiti, group_id: str) -> Dict[str, int]:
        """统计图谱节点和边数"""
        try:
            records, _, _ = await graphiti.driver.execute_query(
                """
                MATCH (n:Entity {group_id: $gid})
                RETURN count(n) AS node_count
                """,
                params={"gid": group_id},
            )
            node_count = records[0]["node_count"] if records else 0

            records, _, _ = await graphiti.driver.execute_query(
                """
                MATCH ()-[e:RELATES_TO {group_id: $gid}]->()
                RETURN count(e) AS edge_count
                """,
                params={"gid": group_id},
            )
            edge_count = records[0]["edge_count"] if records else 0

            return {"node_count": node_count, "edge_count": edge_count}
        except Exception:
            return {"node_count": 0, "edge_count": 0}

    async def _save_project_meta(self, graphiti: Graphiti, group_id: str, graph_name: str):
        """在 Neo4j 中保存项目元数据（名称等），用于列表展示。"""
        try:
            await graphiti.driver.execute_query(
                """
                MERGE (p:GraphProject {group_id: $gid})
                SET p.name = $name,
                    p.created_at = datetime()
                """,
                params={"gid": group_id, "name": graph_name},
            )
        except Exception as e:
            logger.warning(f"保存项目元数据失败: {e}")

    def _build_type_dicts(self, ontology: Dict[str, Any]):
        """从本体定义中构建 Graphiti 所需的 entity_types 和 edge_types 字典。"""
        def _coerce_to_str(v):
            if v is None:
                return v
            return str(v)

        CoercedStr = Annotated[Optional[str], BeforeValidator(_coerce_to_str)]

        entity_types_dict = {}
        edge_types_dict = {}

        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")

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
