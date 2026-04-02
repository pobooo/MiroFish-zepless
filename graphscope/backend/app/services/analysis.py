from __future__ import annotations

from collections import defaultdict
from statistics import mean

import networkx as nx

from app.models.schemas import (
    CommunityItem,
    GlobalMetrics,
    GraphData,
    GraphMetricsResponse,
    ImportantNodeItem,
    NodeMetricItem,
)


class GraphAnalysisService:
    SUPPORTED_RANKINGS = (
        "degree_centrality",
        "pagerank",
        "betweenness_centrality",
        "closeness_centrality",
        "eigenvector_centrality",
        "katz_centrality",
        "harmonic_centrality",
        "clustering_coefficient",
        "core_number",
        "hits_hub",
        "hits_authority",
    )

    def build_graph(self, data: GraphData) -> nx.DiGraph:
        graph = nx.DiGraph(graph_id=data.graph_id)
        for node in data.nodes:
            graph.add_node(
                node.id,
                name=node.name,
                labels=node.labels,
                group_id=node.group_id,
                summary=node.summary,
                attributes=node.attributes,
            )
        for edge in data.edges:
            if edge.source not in graph or edge.target not in graph:
                continue
            graph.add_edge(
                edge.source,
                edge.target,
                id=edge.id,
                name=edge.name,
                fact=edge.fact,
                group_id=edge.group_id,
                weight=edge.weight or 1.0,
                attributes=edge.attributes,
            )
        return graph

    def _normalize_scores(self, scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        values = list(scores.values())
        min_value = min(values)
        max_value = max(values)
        if max_value == min_value:
            return {key: 1.0 for key in scores}
        return {key: (value - min_value) / (max_value - min_value) for key, value in scores.items()}

    def _to_items(self, graph: nx.DiGraph, metric: str, scores: dict[str, float], top_k: int = 10) -> list[NodeMetricItem]:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        items: list[NodeMetricItem] = []
        for node_id, score in ordered:
            node_data = graph.nodes[node_id]
            items.append(
                NodeMetricItem(
                    node_id=node_id,
                    name=node_data.get("name", node_id),
                    score=round(float(score), 6),
                    metric=metric,
                    group_id=node_data.get("group_id"),
                    labels=node_data.get("labels", []),
                )
            )
        return items

    def compute_rankings(self, graph: nx.DiGraph, top_k: int = 10) -> dict[str, list[NodeMetricItem]]:
        if graph.number_of_nodes() == 0:
            return {metric: [] for metric in self.SUPPORTED_RANKINGS}

        undirected = graph.to_undirected()
        # 移除自环（部分算法如 core_number 不允许自环）
        undirected.remove_edges_from(nx.selfloop_edges(undirected))
        rankings: dict[str, dict[str, float]] = {
            "degree_centrality": nx.degree_centrality(undirected),
            "pagerank": nx.pagerank(graph, weight="weight"),
            "betweenness_centrality": nx.betweenness_centrality(graph, weight="weight", normalized=True),
            "closeness_centrality": nx.closeness_centrality(graph),
        }
        try:
            rankings["eigenvector_centrality"] = nx.eigenvector_centrality_numpy(graph, weight="weight")
        except Exception:
            rankings["eigenvector_centrality"] = {node: 0.0 for node in graph.nodes}

        # ---- 新增指标 ----
        # Katz Centrality
        try:
            rankings["katz_centrality"] = nx.katz_centrality_numpy(graph, weight="weight")
        except Exception:
            rankings["katz_centrality"] = {node: 0.0 for node in graph.nodes}

        # Harmonic Centrality（改进版 Closeness，处理非连通图更稳健）
        rankings["harmonic_centrality"] = nx.harmonic_centrality(undirected)

        # Clustering Coefficient（节点邻居互连程度）
        clustering = nx.clustering(undirected)
        rankings["clustering_coefficient"] = clustering

        # Core Number（K-Core 层数）
        core_numbers = nx.core_number(undirected)
        # 转为浮点数以兼容排序
        rankings["core_number"] = {node: float(v) for node, v in core_numbers.items()}

        # HITS: Hub 和 Authority 分数
        try:
            hubs, authorities = nx.hits(graph, max_iter=200, normalized=True)
            rankings["hits_hub"] = hubs
            rankings["hits_authority"] = authorities
        except Exception:
            rankings["hits_hub"] = {node: 0.0 for node in graph.nodes}
            rankings["hits_authority"] = {node: 0.0 for node in graph.nodes}

        # 返回所有节点的排行数据，前端负责按类型过滤后再截断 top_k
        return {
            metric: self._to_items(graph, metric, scores, top_k=graph.number_of_nodes())
            for metric, scores in rankings.items()
        }

    def compute_global_metrics(self, graph: nx.DiGraph) -> GlobalMetrics:
        node_count = graph.number_of_nodes()
        edge_count = graph.number_of_edges()
        undirected = graph.to_undirected()
        # 移除自环
        undirected.remove_edges_from(nx.selfloop_edges(undirected))

        if node_count == 0:
            return GlobalMetrics(
                node_count=0,
                edge_count=0,
                density=0,
                average_degree=0,
                average_clustering=0,
                connected_components=0,
                largest_component_size=0,
                average_shortest_path_length=None,
                diameter=None,
                bridge_edge_count=0,
                transitivity=0,
                assortativity=None,
                modularity=None,
                max_core_number=0,
            )

        components = list(nx.connected_components(undirected)) if undirected.number_of_nodes() else []
        largest_component_nodes = max(components, key=len) if components else set()
        largest_component = undirected.subgraph(largest_component_nodes).copy() if largest_component_nodes else undirected

        average_shortest_path_length = None
        diameter = None
        if largest_component.number_of_nodes() > 1:
            average_shortest_path_length = round(nx.average_shortest_path_length(largest_component), 6)
            diameter = nx.diameter(largest_component)

        average_degree = mean(dict(undirected.degree()).values()) if undirected.number_of_nodes() else 0

        # ---- 新增全局指标 ----
        # Transitivity（全局聚类系数 / 三角形闭合比例）
        transitivity = round(nx.transitivity(undirected), 6) if undirected.number_of_nodes() else 0

        # Assortativity（度-度相关性，同配性）
        assortativity = None
        try:
            if undirected.number_of_edges() > 0:
                assortativity = round(nx.degree_assortativity_coefficient(undirected), 6)
        except Exception:
            pass

        # Modularity（基于 Louvain 社区的模块度）
        modularity = None
        try:
            if undirected.number_of_nodes() > 1:
                communities = list(nx.community.louvain_communities(undirected, weight="weight", seed=42))
                modularity = round(nx.community.modularity(undirected, communities), 6)
        except Exception:
            pass

        # Max K-Core Number
        max_core_number = 0
        try:
            core_numbers = nx.core_number(undirected)
            max_core_number = max(core_numbers.values()) if core_numbers else 0
        except Exception:
            pass

        return GlobalMetrics(
            node_count=node_count,
            edge_count=edge_count,
            density=round(nx.density(graph), 6),
            average_degree=round(float(average_degree), 6),
            average_clustering=round(nx.average_clustering(undirected), 6) if undirected.number_of_nodes() else 0,
            connected_components=len(components),
            largest_component_size=len(largest_component_nodes),
            average_shortest_path_length=average_shortest_path_length,
            diameter=diameter,
            bridge_edge_count=len(list(nx.bridges(undirected))) if undirected.number_of_nodes() else 0,
            transitivity=transitivity,
            assortativity=assortativity,
            modularity=modularity,
            max_core_number=max_core_number,
        )

    def detect_communities(self, graph: nx.DiGraph, algorithm: str = "louvain", top_k_core: int = 3) -> list[CommunityItem]:
        undirected = graph.to_undirected()
        if undirected.number_of_nodes() == 0:
            return []

        if algorithm == "label_propagation":
            raw_communities = list(nx.community.asyn_lpa_communities(undirected, weight="weight", seed=42))
        else:
            raw_communities = list(nx.community.louvain_communities(undirected, weight="weight", seed=42))

        pagerank_scores = nx.pagerank(graph, weight="weight") if graph.number_of_nodes() else {}
        communities: list[CommunityItem] = []
        for idx, members in enumerate(raw_communities):
            subgraph = undirected.subgraph(members)
            core_members = sorted(members, key=lambda node_id: pagerank_scores.get(node_id, 0.0), reverse=True)[:top_k_core]
            communities.append(
                CommunityItem(
                    community_id=idx,
                    size=len(members),
                    density=round(nx.density(subgraph), 6) if subgraph.number_of_nodes() > 1 else 0.0,
                    core_nodes=self._to_items(
                        graph,
                        metric="pagerank",
                        scores={node_id: pagerank_scores.get(node_id, 0.0) for node_id in core_members},
                        top_k=top_k_core,
                    ),
                    member_node_ids=sorted(members),
                )
            )
        communities.sort(key=lambda item: item.size, reverse=True)
        return communities

    def find_important_nodes(self, graph: nx.DiGraph, top_k: int = 10) -> list[ImportantNodeItem]:
        rankings = self.compute_rankings(graph, top_k=graph.number_of_nodes())
        metric_maps: dict[str, dict[str, float]] = defaultdict(dict)
        for metric, items in rankings.items():
            for item in items:
                metric_maps[metric][item.node_id] = item.score

        normalized_maps = {
            metric: self._normalize_scores(scores)
            for metric, scores in metric_maps.items()
        }
        aggregated_scores: dict[str, float] = defaultdict(float)
        for metric, scores in normalized_maps.items():
            weight = 1.4 if metric in {"pagerank", "betweenness_centrality"} else 1.0
            for node_id, score in scores.items():
                aggregated_scores[node_id] += score * weight

        # 返回所有节点的综合评分，前端负责按类型过滤后再截断 top_k
        important_nodes: list[ImportantNodeItem] = []
        for node_id, final_score in sorted(aggregated_scores.items(), key=lambda item: item[1], reverse=True):
            node_data = graph.nodes[node_id]
            metrics = {
                metric: round(metric_maps.get(metric, {}).get(node_id, 0.0), 6)
                for metric in self.SUPPORTED_RANKINGS
            }
            reasons = []
            if metrics["pagerank"] > 0:
                reasons.append("全局连接影响力高")
            if metrics["betweenness_centrality"] > 0:
                reasons.append("跨社区桥接能力强")
            if metrics["degree_centrality"] > 0:
                reasons.append("直接连接节点较多")
            important_nodes.append(
                ImportantNodeItem(
                    node_id=node_id,
                    name=node_data.get("name", node_id),
                    score=round(final_score, 6),
                    metric="importance_score",
                    group_id=node_data.get("group_id"),
                    labels=node_data.get("labels", []),
                    reasons=reasons[:3],
                    metrics=metrics,
                )
            )
        return important_nodes

    def analyze(self, data: GraphData, top_k: int = 10, community_algorithm: str = "louvain") -> GraphMetricsResponse:
        graph = self.build_graph(data)
        rankings = self.compute_rankings(graph, top_k=top_k)
        communities = self.detect_communities(graph, algorithm=community_algorithm)
        important_nodes = self.find_important_nodes(graph, top_k=top_k)
        return GraphMetricsResponse(
            graph_id=data.graph_id,
            global_metrics=self.compute_global_metrics(graph),
            rankings=rankings,
            communities=communities,
            important_nodes=important_nodes,
        )
