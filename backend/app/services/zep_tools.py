"""
图谱检索工具服务（Graphiti 实现）
封装图谱搜索、节点读取、边查询等工具，供Report Agent使用

保留文件名和类名以保持向后兼容的 import 路径，
内部实现已完全替换为 Graphiti API。

核心检索工具：
1. InsightForge（深度洞察检索）- 最强大的混合检索，自动生成子问题并多维度检索
2. PanoramaSearch（广度搜索）- 获取全貌，包括过期内容
3. QuickSearch（简单搜索）- 快速检索
"""

import asyncio
import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode as GraphitiEntityNode
from graphiti_core.edges import EntityEdge as GraphitiEntityEdge

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges, fetch_node_edges

logger = get_logger('mirofish.zep_tools')


def _run_async(coro):
    """在同步代码中运行异步协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


@dataclass
class SearchResult:
    """搜索结果"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式，供LLM理解"""
        text_parts = [f"搜索查询: {self.query}", f"找到 {self.total_count} 条相关信息"]
        
        if self.facts:
            text_parts.append("\n### 相关事实:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """节点信息"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """转换为文本格式"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node", "Episodic"]), "未知类型")
        return f"实体: {self.name} (类型: {entity_type})\n摘要: {self.summary}"


@dataclass
class EdgeInfo:
    """边信息"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # 时间信息
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """转换为文本格式"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"关系: {source} --[{self.name}]--> {target}\n事实: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or "未知"
            invalid_at = self.invalid_at or "至今"
            base_text += f"\n时效: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (已过期: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """是否已过期"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """是否已失效"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """深度洞察检索结果 (InsightForge)"""
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    semantic_facts: List[str] = field(default_factory=list)
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)
    relationship_chains: List[str] = field(default_factory=list)
    
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """转换为详细的文本格式"""
        text_parts = [
            f"## 未来预测深度分析",
            f"分析问题: {self.query}",
            f"预测场景: {self.simulation_requirement}",
            f"\n### 预测数据统计",
            f"- 相关预测事实: {self.total_facts}条",
            f"- 涉及实体: {self.total_entities}个",
            f"- 关系链: {self.total_relationships}条"
        ]
        
        if self.sub_queries:
            text_parts.append(f"\n### 分析的子问题")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        if self.semantic_facts:
            text_parts.append(f"\n### 【关键事实】(请在报告中引用这些原文)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f'{i}. "{fact}"')
        
        if self.entity_insights:
            text_parts.append(f"\n### 【核心实体】")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', '未知')}** ({entity.get('type', '实体')})")
                if entity.get('summary'):
                    text_parts.append(f'  摘要: "{entity.get("summary")}"')
                if entity.get('related_facts'):
                    text_parts.append(f"  相关事实: {len(entity.get('related_facts', []))}条")
        
        if self.relationship_chains:
            text_parts.append(f"\n### 【关系链】")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """广度搜索结果 (Panorama)"""
    query: str
    
    all_nodes: List[NodeInfo] = field(default_factory=list)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    active_facts: List[str] = field(default_factory=list)
    historical_facts: List[str] = field(default_factory=list)
    
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """转换为文本格式"""
        text_parts = [
            f"## 广度搜索结果（未来全景视图）",
            f"查询: {self.query}",
            f"\n### 统计信息",
            f"- 总节点数: {self.total_nodes}",
            f"- 总边数: {self.total_edges}",
            f"- 当前有效事实: {self.active_count}条",
            f"- 历史/过期事实: {self.historical_count}条"
        ]
        
        if self.active_facts:
            text_parts.append(f"\n### 【当前有效事实】(模拟结果原文)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f'{i}. "{fact}"')
        
        if self.historical_facts:
            text_parts.append(f"\n### 【历史/过期事实】(演变过程记录)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f'{i}. "{fact}"')
        
        if self.all_nodes:
            text_parts.append(f"\n### 【涉及实体】")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node", "Episodic"]), "实体")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """单个Agent的采访结果"""
    agent_name: str
    agent_role: str
    agent_bio: str
    question: str
    response: str
    key_quotes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        text += f"_简介: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**关键引言:**\n"
            for quote in self.key_quotes:
                import re
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                while clean_quote and clean_quote[0] in '，,；;：:、。！？\n\r\t ':
                    clean_quote = clean_quote[1:]
                skip = False
                for d in '123456789':
                    if f'\u95ee\u9898{d}' in clean_quote:
                        skip = True
                        break
                if skip:
                    continue
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """采访结果 (Interview)"""
    interview_topic: str
    interview_questions: List[str]
    
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    interviews: List[AgentInterview] = field(default_factory=list)
    
    selection_reasoning: str = ""
    summary: str = ""
    
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """转换为详细的文本格式"""
        text_parts = [
            "## 深度采访报告",
            f"**采访主题:** {self.interview_topic}",
            f"**采访人数:** {self.interviewed_count} / {self.total_agents} 位模拟Agent",
            "\n### 采访对象选择理由",
            self.selection_reasoning or "（自动选择）",
            "\n---",
            "\n### 采访实录",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### 采访 #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append("（无采访记录）\n\n---")

        text_parts.append("\n### 采访摘要与核心观点")
        text_parts.append(self.summary or "（无摘要）")

        return "\n".join(text_parts)


class ZepToolsService:
    """
    图谱检索工具服务（Graphiti 实现）
    
    保留类名 ZepToolsService 以保持向后兼容。
    """
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        # api_key 参数保留以兼容旧代码，不再使用
        self._graphiti: Optional[Graphiti] = None
        self._llm_client = llm_client
        logger.info("ZepToolsService 初始化完成（Graphiti 后端）")
    
    async def _get_client(self) -> Graphiti:
        """获取 Graphiti 客户端"""
        if self._graphiti is None:
            from graphiti.graphiti_client import get_graphiti_client
            self._graphiti = await get_graphiti_client()
        return self._graphiti
    
    @property
    def llm(self) -> LLMClient:
        """延迟初始化LLM客户端"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        图谱语义搜索（使用 Graphiti 混合搜索）
        """
        return _run_async(self._search_graph_async(graph_id, query, limit, scope))
    
    async def _search_graph_async(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """图谱搜索异步实现"""
        logger.info(f"图谱搜索: graph_id={graph_id}, query={query[:50]}...")
        
        graphiti = await self._get_client()
        
        facts = []
        edges = []
        nodes = []
        
        try:
            if scope in ["edges", "both"]:
                # 使用 Graphiti search API 搜索边
                search_edges = await graphiti.search(
                    query=query,
                    group_ids=[graph_id] if graph_id else None,
                    num_results=limit,
                )
                
                for edge in search_edges:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": edge.uuid,
                        "name": edge.name or "",
                        "fact": edge.fact or "",
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # 使用 search_ 获取节点搜索结果
                from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
                search_results = await graphiti.search_(
                    query=query,
                    config=NODE_HYBRID_SEARCH_RRF,
                    group_ids=[graph_id] if graph_id else None,
                )
                
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": node.uuid,
                        "name": node.name or "",
                        "labels": node.labels or [],
                        "summary": node.summary or "",
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"搜索完成: 找到 {len(facts)} 条相关事实")
            
        except Exception as e:
            logger.warning(f"Graphiti Search API失败，降级为本地搜索: {str(e)}")
            return await self._local_search_async(graph_id, query, limit, scope)
        
        return SearchResult(
            facts=facts,
            edges=edges,
            nodes=nodes,
            query=query,
            total_count=len(facts)
        )
    
    async def _local_search_async(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """本地关键词匹配搜索（降级方案）"""
        logger.info(f"使用本地搜索: query={query[:30]}...")
        
        facts = []
        edges_result = []
        nodes_result = []
        
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            if not text:
                return 0
            text_lower = text.lower()
            if query_lower in text_lower:
                return 100
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            graphiti = await self._get_client()
            
            if scope in ["edges", "both"]:
                all_edges = await self._get_all_edges_async(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                all_nodes = await self._get_all_nodes_async(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
        except Exception as e:
            logger.error(f"本地搜索失败: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    # ========== 基础工具方法 ==========
    
    async def _get_all_nodes_async(self, graph_id: str) -> List[GraphitiEntityNode]:
        """获取所有节点（原始 Graphiti 对象）"""
        graphiti = await self._get_client()
        return await fetch_all_nodes(graphiti, group_id=graph_id)
    
    async def _get_all_edges_async(self, graph_id: str) -> List[GraphitiEntityEdge]:
        """获取所有边（原始 Graphiti 对象）"""
        graphiti = await self._get_client()
        return await fetch_all_edges(graphiti, group_id=graph_id)
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """获取图谱的所有节点"""
        return _run_async(self._get_all_nodes_info_async(graph_id))
    
    async def _get_all_nodes_info_async(self, graph_id: str) -> List[NodeInfo]:
        """获取所有节点信息"""
        logger.info(f"获取图谱 {graph_id} 的所有节点...")
        nodes = await self._get_all_nodes_async(graph_id)
        
        result = []
        for node in nodes:
            result.append(NodeInfo(
                uuid=node.uuid,
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))
        
        logger.info(f"获取到 {len(result)} 个节点")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """获取图谱的所有边"""
        return _run_async(self._get_all_edges_info_async(graph_id, include_temporal))
    
    async def _get_all_edges_info_async(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """获取所有边信息"""
        logger.info(f"获取图谱 {graph_id} 的所有边...")
        edges = await self._get_all_edges_async(graph_id)
        
        result = []
        for edge in edges:
            edge_info = EdgeInfo(
                uuid=edge.uuid,
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )
            
            if include_temporal:
                edge_info.created_at = str(edge.created_at) if edge.created_at else None
                edge_info.valid_at = str(edge.valid_at) if edge.valid_at else None
                edge_info.invalid_at = str(edge.invalid_at) if edge.invalid_at else None
                edge_info.expired_at = str(edge.expired_at) if edge.expired_at else None
            
            result.append(edge_info)
        
        logger.info(f"获取到 {len(result)} 条边")
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """获取单个节点的详细信息"""
        return _run_async(self._get_node_detail_async(node_uuid))
    
    async def _get_node_detail_async(self, node_uuid: str) -> Optional[NodeInfo]:
        """获取节点详情异步实现"""
        logger.info(f"获取节点详情: {node_uuid[:8]}...")
        try:
            graphiti = await self._get_client()
            node = await GraphitiEntityNode.get_by_uuid(graphiti.driver, node_uuid)
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=node.uuid,
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"获取节点详情失败: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """获取节点相关的所有边"""
        return _run_async(self._get_node_edges_info_async(graph_id, node_uuid))
    
    async def _get_node_edges_info_async(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """获取节点边信息"""
        logger.info(f"获取节点 {node_uuid[:8]}... 的相关边")
        try:
            graphiti = await self._get_client()
            edges = await fetch_node_edges(graphiti, node_uuid)
            
            result = []
            for edge in edges:
                result.append(EdgeInfo(
                    uuid=edge.uuid,
                    name=edge.name or "",
                    fact=edge.fact or "",
                    source_node_uuid=edge.source_node_uuid or "",
                    target_node_uuid=edge.target_node_uuid or "",
                    created_at=str(edge.created_at) if edge.created_at else None,
                    valid_at=str(edge.valid_at) if edge.valid_at else None,
                    invalid_at=str(edge.invalid_at) if edge.invalid_at else None,
                    expired_at=str(edge.expired_at) if edge.expired_at else None,
                ))
            
            logger.info(f"找到 {len(result)} 条与节点相关的边")
            return result
        except Exception as e:
            logger.warning(f"获取节点边失败: {str(e)}")
            return []
    
    def get_entities_by_type(self, graph_id: str, entity_type: str) -> List[NodeInfo]:
        """按类型获取实体"""
        logger.info(f"获取类型为 {entity_type} 的实体...")
        all_nodes = self.get_all_nodes(graph_id)
        filtered = [node for node in all_nodes if entity_type in node.labels]
        logger.info(f"找到 {len(filtered)} 个 {entity_type} 类型的实体")
        return filtered
    
    def get_entity_summary(self, graph_id: str, entity_name: str) -> Dict[str, Any]:
        """获取指定实体的关系摘要"""
        logger.info(f"获取实体 {entity_name} 的关系摘要...")
        
        search_result = self.search_graph(graph_id=graph_id, query=entity_name, limit=20)
        
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """获取图谱的统计信息"""
        logger.info(f"获取图谱 {graph_id} 的统计信息...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node", "Episodic"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(self, graph_id: str, simulation_requirement: str, limit: int = 30) -> Dict[str, Any]:
        """获取模拟相关的上下文信息"""
        logger.info(f"获取模拟上下文: {simulation_requirement[:50]}...")
        
        search_result = self.search_graph(graph_id=graph_id, query=simulation_requirement, limit=limit)
        stats = self.get_graph_statistics(graph_id)
        all_nodes = self.get_all_nodes(graph_id)
        
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node", "Episodic"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],
            "total_entities": len(entities)
        }
    
    # ========== 核心检索工具 ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """【InsightForge - 深度洞察检索】"""
        logger.info(f"InsightForge 深度洞察检索: {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: 使用LLM生成子问题
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"生成 {len(sub_queries)} 个子问题")
        
        # Step 2: 对每个子问题进行语义搜索
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(graph_id=graph_id, query=sub_query, limit=15, scope="edges")
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            all_edges.extend(search_result.edges)
        
        # 对原始问题也进行搜索
        main_search = self.search_graph(graph_id=graph_id, query=query, limit=20, scope="edges")
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Step 3: 提取相关实体
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                if edge_data.get('source_node_uuid'):
                    entity_uuids.add(edge_data['source_node_uuid'])
                if edge_data.get('target_node_uuid'):
                    entity_uuids.add(edge_data['target_node_uuid'])
        
        entity_insights = []
        node_map = {}
        
        for uuid_val in list(entity_uuids):
            if not uuid_val:
                continue
            try:
                node = self.get_node_detail(uuid_val)
                if node:
                    node_map[uuid_val] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node", "Episodic"]), "实体")
                    related_facts = [f for f in all_facts if node.name.lower() in f.lower()]
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts
                    })
            except Exception as e:
                logger.debug(f"获取节点 {uuid_val} 失败: {e}")
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: 构建关系链
        relationship_chains = []
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForge完成: {result.total_facts}条事实, {result.total_entities}个实体, {result.total_relationships}条关系")
        return result
    
    def _generate_sub_queries(self, query: str, simulation_requirement: str, report_context: str = "", max_queries: int = 5) -> List[str]:
        """使用LLM生成子问题"""
        system_prompt = """你是一个专业的问题分析专家。你的任务是将一个复杂问题分解为多个可以在模拟世界中独立观察的子问题。

要求：
1. 每个子问题应该足够具体
2. 子问题应该覆盖原问题的不同维度
3. 子问题应该与模拟场景相关
4. 返回JSON格式：{"sub_queries": ["子问题1", "子问题2", ...]}"""

        user_prompt = f"""模拟需求背景：
{simulation_requirement}

{f"报告上下文：{report_context[:500]}" if report_context else ""}

请将以下问题分解为{max_queries}个子问题：
{query}

返回JSON格式的子问题列表。"""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            sub_queries = response.get("sub_queries", [])
            return [str(sq) for sq in sub_queries[:max_queries]]
        except Exception as e:
            logger.warning(f"生成子问题失败: {str(e)}，使用默认子问题")
            return [query, f"{query} 的主要参与者", f"{query} 的原因和影响", f"{query} 的发展过程"][:max_queries]
    
    def panorama_search(self, graph_id: str, query: str, include_expired: bool = True, limit: int = 50) -> PanoramaResult:
        """【PanoramaSearch - 广度搜索】"""
        logger.info(f"PanoramaSearch 广度搜索: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                valid_at = edge.valid_at or "未知"
                invalid_at = edge.invalid_at or edge.expired_at or "未知"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                active_facts.append(edge.fact)
        
        # 相关性排序
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearch完成: {result.active_count}条有效, {result.historical_count}条历史")
        return result
    
    def quick_search(self, graph_id: str, query: str, limit: int = 10) -> SearchResult:
        """【QuickSearch - 简单搜索】"""
        logger.info(f"QuickSearch 简单搜索: {query[:50]}...")
        result = self.search_graph(graph_id=graph_id, query=query, limit=limit, scope="edges")
        logger.info(f"QuickSearch完成: {result.total_count}条结果")
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        【InterviewAgents - 深度采访】
        此方法调用 OASIS 采访 API，不依赖 Zep/Graphiti，保持不变。
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents 深度采访: {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Step 1: 读取人设文件
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"未找到模拟 {simulation_id} 的人设文件")
            result.summary = "未找到可采访的Agent人设文件"
            return result
        
        result.total_agents = len(profiles)
        
        # Step 2: 选择Agent
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        
        # Step 3: 生成采访问题
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
        
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        INTERVIEW_PROMPT_PREFIX = (
            "你正在接受一次采访。请结合你的人设、所有的过往记忆与行动，"
            "以纯文本方式直接回答以下问题。\n"
            "回复要求：\n"
            "1. 直接用自然语言回答，不要调用任何工具\n"
            "2. 不要返回JSON格式或工具调用格式\n"
            "3. 不要使用Markdown标题（如#、##、###）\n"
            "4. 按问题编号逐一回答，每个回答以「问题X：」开头（X为问题编号）\n"
            "5. 每个问题的回答之间用空行分隔\n"
            "6. 回答要有实质内容，每个问题至少回答2-3句话\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: 调用采访API
        try:
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt
                })
            
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,
                timeout=180.0
            )
            
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "未知错误")
                result.summary = f"采访API调用失败：{error_msg}。请检查OASIS模拟环境状态。"
                return result
            
            # Step 5: 解析结果
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "未知")
                agent_bio = agent.get("bio", "")
                
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = self._clean_tool_call_response(twitter_result.get("response", ""))
                reddit_response = self._clean_tool_call_response(reddit_result.get("response", ""))
                
                twitter_text = twitter_response if twitter_response else "（该平台未获得回复）"
                reddit_text = reddit_response if reddit_response else "（该平台未获得回复）"
                response_text = f"【Twitter平台回答】\n{twitter_text}\n\n【Reddit平台回答】\n{reddit_text}"
                
                import re
                combined_responses = f"{twitter_response} {reddit_response}"
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'问题\d+[：:]\s*', '', clean_text)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)
                
                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not s.strip().startswith(('{', '问题'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]
                
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            result.summary = f"采访失败：{str(e)}。模拟环境可能已关闭。"
            return result
        except Exception as e:
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"采访过程发生错误：{str(e)}"
            return result
        
        # Step 6: 生成摘要
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgents完成: 采访了 {result.interviewed_count} 个Agent")
        return result
    
    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """清理 Agent 回复中的 JSON 工具调用包裹"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """加载模拟的Agent人设文件"""
        import os
        import csv
        
        sim_dir = os.path.join(os.path.dirname(__file__), f'../../uploads/simulations/{simulation_id}')
        profiles = []
        
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                return profiles
            except Exception as e:
                logger.warning(f"读取 reddit_profiles.json 失败: {e}")
        
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "未知"
                        })
                return profiles
            except Exception as e:
                logger.warning(f"读取 twitter_profiles.csv 失败: {e}")
        
        return profiles
    
    def _select_agents_for_interview(self, profiles, interview_requirement, simulation_requirement, max_agents):
        """使用LLM选择要采访的Agent"""
        agent_summaries = []
        for i, profile in enumerate(profiles):
            agent_summaries.append({
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "未知"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            })
        
        system_prompt = """你是一个专业的采访策划专家。根据采访需求选择最适合的Agent。
返回JSON格式：{"selected_indices": [索引列表], "reasoning": "选择理由"}"""

        user_prompt = f"""采访需求：{interview_requirement}
模拟背景：{simulation_requirement if simulation_requirement else "未提供"}
Agent列表：{json.dumps(agent_summaries, ensure_ascii=False)}
选择最多{max_agents}个。"""

        try:
            response = self.llm.chat_json(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.3
            )
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "基于相关性自动选择")
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            return selected_agents, valid_indices, reasoning
        except Exception as e:
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "使用默认选择策略"
    
    def _generate_interview_questions(self, interview_requirement, simulation_requirement, selected_agents):
        """生成采访问题"""
        agent_roles = [a.get("profession", "未知") for a in selected_agents]
        
        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": "你是专业记者。生成3-5个采访问题。返回JSON：{\"questions\": [...]}"},
                    {"role": "user", "content": f"采访需求：{interview_requirement}\n角色：{', '.join(agent_roles)}"}
                ],
                temperature=0.5
            )
            return response.get("questions", [f"关于{interview_requirement}，您有什么看法？"])
        except Exception as e:
            return [f"关于{interview_requirement}，您的观点是什么？", "这件事对您有什么影响？", "您认为应该如何改进？"]
    
    def _generate_interview_summary(self, interviews, interview_requirement):
        """生成采访摘要"""
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"【{interview.agent_name}（{interview.agent_role}）】\n{interview.response[:500]}")
        
        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": "你是专业新闻编辑。根据采访回答生成摘要，1000字内，纯文本格式。"},
                    {"role": "user", "content": f"主题：{interview_requirement}\n\n{''.join(interview_texts)}"}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
        except Exception as e:
            return f"共采访了{len(interviews)}位受访者：" + "、".join([i.agent_name for i in interviews])
