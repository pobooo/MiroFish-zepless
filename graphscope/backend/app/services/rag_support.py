from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import networkx as nx

from app.core.config import get_settings
from app.models.schemas import GraphData, GraphEdge, GraphNode, GraphPathResponse, RAGContextRequest, RAGContextResponse
from app.services.analysis import GraphAnalysisService


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
        query_terms = [term.strip().lower() for term in query.split() if term.strip()]
        if not query_terms:
            return {}

        scores: dict[str, float] = defaultdict(float)
        for node in data.nodes:
            haystack = " ".join(filter(None, [node.name, node.summary or ""]))
            text = haystack.lower()
            for term in query_terms:
                scores[node.id] += text.count(term) * 2
        for edge in data.edges:
            edge_text = " ".join(filter(None, [edge.name or "", edge.fact or ""])).lower()
            for term in query_terms:
                count = edge_text.count(term)
                if count:
                    scores[edge.source] += count
                    scores[edge.target] += count
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
            matched_communities = []
            seed_node_ids = {node_id for node_id, score in seed_scores.items() if score > 0}
            for community in communities:
                members = set(community.member_node_ids)
                if members & seed_node_ids:
                    matched_communities.append(community)
            if not matched_communities:
                matched_communities = communities[:2]
            for community in matched_communities[:2]:
                selected_node_ids.update(community.member_node_ids[: request.max_nodes])
                citations.append(
                    f"社区 {community.community_id}: 核心节点 {', '.join(node.name for node in community.core_nodes)}"
                )

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
