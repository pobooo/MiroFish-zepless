from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations

import networkx as nx

from app.core.config import get_settings
from app.models.schemas import GraphData, GraphEdge, GraphNode, GraphPathResponse, RAGContextRequest, RAGContextResponse
from app.services.analysis import GraphAnalysisService

# ---------------------------------------------------------------------------
# 中英文混合分词工具（无外部依赖）
# ---------------------------------------------------------------------------
_RE_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_RE_WORD = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff\u3400-\u4dbf]")


def _tokenize(text: str) -> list[str]:
    """将中英文混合文本拆分为 token 列表。

    英文 / 数字按完整单词切分，中文按**单字**切分。
    返回值全部小写，去重保序。
    """
    tokens: list[str] = []
    seen: set[str] = set()
    for m in _RE_WORD.finditer(text.lower()):
        tok = m.group()
        if tok not in seen:
            seen.add(tok)
            tokens.append(tok)
    return tokens


def _cjk_bigrams(text: str) -> list[str]:
    """提取连续中文双字组合（bigram），用于在较长文本中做短语匹配。"""
    chars = [ch for ch in text if _RE_CJK.match(ch)]
    bigrams: list[str] = []
    seen: set[str] = set()
    for i in range(len(chars) - 1):
        bg = chars[i] + chars[i + 1]
        if bg not in seen:
            seen.add(bg)
            bigrams.append(bg)
    return bigrams


class GraphRAGSupportService:
    def __init__(self, analysis_service: GraphAnalysisService):
        self.analysis_service = analysis_service
        self.settings = get_settings()

    def _resolve_identifier(self, graph: nx.DiGraph, identifier: str) -> str | None:
        if identifier in graph:
            return identifier
        identifier_lower = identifier.lower()
        for node_id, attrs in graph.nodes(data=True):
            if attrs.get("name", "").lower() == identifier_lower:
                return node_id
        return None

    def _query_seed_scores(self, data: GraphData, query: str) -> dict[str, float]:
        """为每个节点计算与查询的相关度分数。

        采用双向匹配策略：
        1. 正向：将查询分词后在节点文本中搜索（与原来相同）
        2. 反向：检查节点名称是否作为子串出现在查询中（对中文尤其有效，
           例如查询 "OpenAI最近有什么进展" 包含节点名 "OpenAI"）
        """
        query_lower = query.lower()

        # --- 分词 ---
        query_tokens = _tokenize(query)
        query_bigrams = _cjk_bigrams(query)
        all_terms = list(dict.fromkeys(query_tokens + query_bigrams))  # 去重保序

        if not all_terms and not query_lower.strip():
            return {}

        scores: dict[str, float] = defaultdict(float)

        for node in data.nodes:
            node_name = (node.name or "").strip()
            node_name_lower = node_name.lower()
            haystack = " ".join(filter(None, [node_name, node.summary or ""]))
            text = haystack.lower()

            # --- 正向匹配：查询 token 在节点文本中出现 ---
            for term in all_terms:
                count = text.count(term)
                if count:
                    scores[node.id] += count * 2

            # --- 反向匹配：节点名称作为子串出现在查询中 ---
            if node_name_lower and len(node_name_lower) >= 2 and node_name_lower in query_lower:
                # 名称越长匹配越精准，给予更高权重
                scores[node.id] += len(node_name_lower) * 3

            # --- 反向匹配：节点名称的单字 token 在查询中出现 ---
            if node_name_lower:
                name_tokens = _tokenize(node_name)
                matched = sum(1 for t in name_tokens if t in query_lower)
                if matched > 0:
                    scores[node.id] += matched * 1.5

        for edge in data.edges:
            edge_text = " ".join(filter(None, [edge.name or "", edge.fact or ""])).lower()

            for term in all_terms:
                count = edge_text.count(term)
                if count:
                    scores[edge.source] += count
                    scores[edge.target] += count

            # 反向：检查边的关系名或 fact 中的关键词是否在查询中
            edge_name_lower = (edge.name or "").lower()
            if edge_name_lower and len(edge_name_lower) >= 2 and edge_name_lower in query_lower:
                scores[edge.source] += len(edge_name_lower) * 2
                scores[edge.target] += len(edge_name_lower) * 2

        return scores

    def _subgraph_payload(self, source_graph: nx.DiGraph, node_ids: set[str]) -> tuple[list[GraphNode], list[GraphEdge]]:
        nodes = []
        edges = []
        for node_id in node_ids:
            attrs = source_graph.nodes[node_id]
            nodes.append(
                GraphNode(
                    id=node_id,
                    name=attrs.get("name", node_id),
                    labels=attrs.get("labels", []),
                    group_id=attrs.get("group_id"),
                    summary=attrs.get("summary"),
                    attributes=attrs.get("attributes", {}),
                )
            )
        for source, target, attrs in source_graph.edges(data=True):
            if source in node_ids and target in node_ids:
                edges.append(
                    GraphEdge(
                        id=attrs.get("id", f"{source}-{target}"),
                        source=source,
                        target=target,
                        name=attrs.get("name"),
                        fact=attrs.get("fact"),
                        group_id=attrs.get("group_id"),
                        weight=float(attrs.get("weight", 1.0)),
                        attributes=attrs.get("attributes", {}),
                    )
                )
        nodes.sort(key=lambda item: item.name.lower())
        return nodes, edges

    def build_context(self, data: GraphData, request: RAGContextRequest) -> RAGContextResponse:
        graph = self.analysis_service.build_graph(data)
        important_nodes = self.analysis_service.find_important_nodes(graph, top_k=request.max_nodes)
        communities = self.analysis_service.detect_communities(graph, algorithm="louvain")
        seed_scores = self._query_seed_scores(data, request.query)
        selected_node_ids: set[str] = set()
        citations: list[str] = []

        if request.strategy == "centrality_aware":
            for item in important_nodes[: request.max_nodes // 2]:
                selected_node_ids.add(item.node_id)
                citations.append(f"重要节点: {item.name}")
            for node_id, _ in sorted(seed_scores.items(), key=lambda item: item[1], reverse=True)[: request.max_nodes // 2]:
                selected_node_ids.add(node_id)
                selected_node_ids.update(graph.successors(node_id))
                selected_node_ids.update(graph.predecessors(node_id))
        elif request.strategy == "path_aware":
            seed_ids = [node_id for node_id, _ in sorted(seed_scores.items(), key=lambda item: item[1], reverse=True)[:4]]
            if len(seed_ids) < 2:
                seed_ids.extend([item.node_id for item in important_nodes[:2]])
            for source, target in combinations(seed_ids[:4], 2):
                try:
                    path = nx.shortest_path(graph.to_undirected(), source=source, target=target)
                    selected_node_ids.update(path)
                    citations.append(f"关键路径: {' -> '.join(graph.nodes[node]['name'] for node in path)}")
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
        else:
            # community_aware 策略：seed 节点 + 邻居 + 所在社区的核心节点
            # 1. 先选 seed 分数最高的节点及其邻居（与查询最相关）
            top_seeds = [
                node_id for node_id, _ in sorted(
                    seed_scores.items(), key=lambda item: item[1], reverse=True
                ) if seed_scores.get(node_id, 0) > 0
            ][: request.max_nodes // 2]

            for node_id in top_seeds:
                selected_node_ids.add(node_id)
                # 加入直接邻居（1-hop）
                selected_node_ids.update(list(graph.successors(node_id))[:3])
                selected_node_ids.update(list(graph.predecessors(node_id))[:3])

            if top_seeds:
                citations.append(
                    f"查询相关节点: {', '.join(graph.nodes[nid].get('name', nid) for nid in top_seeds[:5])}"
                )

            # 2. 补充社区核心节点（优先匹配 seed 所在社区）
            seed_node_ids = set(top_seeds)
            matched_communities = []
            for community in communities:
                members = set(community.member_node_ids)
                if members & seed_node_ids:
                    matched_communities.append(community)
            if not matched_communities:
                matched_communities = communities[:2]

            remaining = request.max_nodes - len(selected_node_ids)
            if remaining > 0:
                for community in matched_communities[:2]:
                    for core_node in community.core_nodes:
                        selected_node_ids.add(core_node.node_id)
                    citations.append(
                        f"社区 {community.community_id}: 核心节点 {', '.join(node.name for node in community.core_nodes)}"
                    )

            # 3. 如果 seed 没匹配到任何节点，用 important_nodes 兜底
            if not top_seeds:
                for item in important_nodes[: request.max_nodes]:
                    selected_node_ids.add(item.node_id)
                citations.append("未匹配到查询相关节点，使用全局重要节点")

        if not selected_node_ids:
            selected_node_ids.update(item.node_id for item in important_nodes[: request.max_nodes])

        if len(selected_node_ids) > request.max_nodes:
            ordered_ids = sorted(
                selected_node_ids,
                key=lambda node_id: seed_scores.get(node_id, 0.0),
                reverse=True,
            )
            selected_node_ids = set(ordered_ids[: request.max_nodes])

        nodes, edges = self._subgraph_payload(graph, selected_node_ids)
        summary_lines = [
            f"查询主题：{request.query}",
            f"策略：{request.strategy}",
            f"选中节点数：{len(nodes)}，选中边数：{len(edges)}",
        ]
        if important_nodes:
            summary_lines.append(
                "全局重要节点：" + ", ".join(node.name for node in important_nodes[:5])
            )
        if communities:
            summary_lines.append(
                "主要社区：" + ", ".join(
                    f"社区{community.community_id}(size={community.size})" for community in communities[:3]
                )
            )

        return RAGContextResponse(
            graph_id=data.graph_id,
            strategy=request.strategy,
            summary="\n".join(summary_lines),
            nodes=nodes,
            edges=edges,
            citations=citations,
        )

    def find_paths(
        self,
        data: GraphData,
        source_identifier: str,
        target_identifier: str,
        max_depth: int | None = None,
    ) -> GraphPathResponse:
        graph = self.analysis_service.build_graph(data)
        source_node_id = self._resolve_identifier(graph, source_identifier)
        target_node_id = self._resolve_identifier(graph, target_identifier)
        if not source_node_id or not target_node_id:
            return GraphPathResponse(
                graph_id=data.graph_id,
                source_node_id=source_identifier,
                target_node_id=target_identifier,
                paths=[],
            )

        cutoff = max_depth or self.settings.shortest_path_cutoff
        paths: list[list[str]] = []
        try:
            for path in nx.all_simple_paths(graph.to_undirected(), source_node_id, target_node_id, cutoff=cutoff):
                rendered = []
                for index, node_id in enumerate(path):
                    rendered.append(graph.nodes[node_id].get("name", node_id))
                    if index < len(path) - 1:
                        edge_data = graph.get_edge_data(path[index], path[index + 1]) or graph.get_edge_data(path[index + 1], path[index]) or {}
                        rendered.append(edge_data.get("name") or edge_data.get("fact") or "关联")
                paths.append(rendered)
                if len(paths) >= 5:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            paths = []

        return GraphPathResponse(
            graph_id=data.graph_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            paths=paths,
        )
