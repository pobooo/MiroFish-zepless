from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from typing import Literal

from app.core.config import get_settings
from app.models.schemas import GraphData, GraphEdge, GraphNode, GraphSummaryResponse, GroupInfo, GroupListResponse, NodeMetricItem
from app.services.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

SelectionMode = Literal["degree_hub", "alphabetical", "random_sample"]


class GraphLoaderService:
    def __init__(self, client: Neo4jClient):
        self.client = client
        self.settings = get_settings()

    def _group_filter(self, alias: str, group_id: str | None) -> tuple[str, dict]:
        if group_id:
            return f"WHERE {alias}.group_id = $group_id", {"group_id": group_id}
        return "", {}

    def resolve_group_id(self, graph_id: str | None = None, group_id: str | None = None) -> str | None:
        explicit_group = graph_id or group_id or self.settings.default_group_id
        if explicit_group:
            return explicit_group

        result = self.client.run_query(
            """
            MATCH (n:Entity)
            WHERE n.group_id IS NOT NULL
            RETURN n.group_id AS group_id, count(*) AS node_count
            ORDER BY node_count DESC
            LIMIT 1
            """
        )
        return result[0]["group_id"] if result else None

    def list_groups(self) -> GroupListResponse:
        """列出 Neo4j 中所有可用的 group_id，及其节点数、边数和标签样本。"""
        rows = self.client.run_query(
            """
            MATCH (n:Entity)
            WHERE n.group_id IS NOT NULL
            WITH n.group_id AS gid,
                 count(n) AS node_count,
                 collect(labels(n)) AS all_label_lists
            WITH gid, node_count,
                 reduce(s = [], lbls IN all_label_lists |
                     s + [lbl IN lbls WHERE NOT lbl IN ['Entity','Node','Episodic']]
                 ) AS flat_labels
            WITH gid, node_count,
                 [lbl IN collect(DISTINCT flat_labels[0]) WHERE lbl IS NOT NULL] AS tmp
            RETURN gid, node_count
            ORDER BY node_count DESC
            """
        )

        groups: list[GroupInfo] = []
        seen: set[str] = set()
        for row in rows:
            gid = row["gid"]
            if gid in seen:
                continue
            seen.add(gid)
            # 单独查边数
            edge_rows = self.client.run_query(
                "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id = $gid RETURN count(e) AS cnt",
                {"gid": gid},
            )
            edge_count = edge_rows[0]["cnt"] if edge_rows else 0
            # 单独查标签样本（简洁可靠）
            label_rows = self.client.run_query(
                """
                MATCH (n:Entity)
                WHERE n.group_id = $gid
                UNWIND labels(n) AS lbl
                WITH lbl WHERE lbl <> 'Entity' AND lbl <> 'Node' AND lbl <> 'Episodic'
                RETURN collect(DISTINCT lbl)[..5] AS labels
                """,
                {"gid": gid},
            )
            label_sample = label_rows[0]["labels"] if label_rows else []
            # 查度数最高的实体名（作为项目概览）
            top_rows = self.client.run_query(
                """
                MATCH (n:Entity)
                WHERE n.group_id = $gid AND n.name IS NOT NULL
                WITH n,
                     size([(n)-[:RELATES_TO]->() | 1]) +
                     size([()-[:RELATES_TO]->(n) | 1]) AS degree
                ORDER BY degree DESC
                LIMIT 3
                RETURN collect(n.name) AS names
                """,
                {"gid": gid},
            )
            top_entities = top_rows[0]["names"] if top_rows else []
            # 查项目名称（从 GraphProject 元数据节点）
            name_rows = self.client.run_query(
                "MATCH (p:GraphProject {group_id: $gid}) RETURN p.name AS name LIMIT 1",
                {"gid": gid},
            )
            project_name = name_rows[0]["name"] if name_rows else None
            groups.append(
                GroupInfo(
                    group_id=gid,
                    project_name=project_name,
                    node_count=row["node_count"],
                    edge_count=edge_count,
                    label_sample=label_sample,
                    top_entities=top_entities,
                )
            )

        return GroupListResponse(groups=groups, total=len(groups))

    def _normalize_value(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            normalized: dict[str, object] = {}
            for key, item in value.items():
                key_str = str(key)
                if "embedding" in key_str.lower():
                    continue
                normalized[key_str] = self._normalize_value(item)
            return normalized
        if isinstance(value, (list, tuple, set)):
            normalized_list = [self._normalize_value(item) for item in value]
            if len(normalized_list) > 64:
                return normalized_list[:64]
            return normalized_list
        if hasattr(value, "iso_format"):
            return value.iso_format()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    # ------------------------------------------------------------------
    # 节点选择策略
    # ------------------------------------------------------------------

    def _select_nodes_alphabetical(
        self, group_id: str | None, max_nodes: int | None,
    ) -> list[dict]:
        """旧策略：按名称字母序 LIMIT，简单但在图结构上无意义。"""
        node_where, params = self._group_filter("n", group_id)
        node_limit_clause = "LIMIT $node_limit" if max_nodes is not None else ""
        if max_nodes is not None:
            params["node_limit"] = max_nodes

        return self.client.run_query(
            f"""
            MATCH (n:Entity)
            {node_where}
            RETURN n.uuid AS id,
                   coalesce(n.name, n.uuid) AS name,
                   labels(n) AS labels,
                   n.group_id AS group_id,
                   n.summary AS summary,
                   properties(n) AS attributes
            ORDER BY name
            {node_limit_clause}
            """,
            params,
        )

    def _select_nodes_random(
        self, group_id: str | None, max_nodes: int | None,
    ) -> list[dict]:
        """随机采样策略：随机选取节点，适合探索性浏览。"""
        node_where, params = self._group_filter("n", group_id)
        node_limit_clause = "LIMIT $node_limit" if max_nodes is not None else ""
        if max_nodes is not None:
            params["node_limit"] = max_nodes

        return self.client.run_query(
            f"""
            MATCH (n:Entity)
            {node_where}
            WITH n, rand() AS r
            ORDER BY r
            RETURN n.uuid AS id,
                   coalesce(n.name, n.uuid) AS name,
                   labels(n) AS labels,
                   n.group_id AS group_id,
                   n.summary AS summary,
                   properties(n) AS attributes
            {node_limit_clause}
            """,
            params,
        )

    def _select_nodes_degree_hub(
        self, group_id: str | None, max_nodes: int | None,
    ) -> list[dict]:
        """
        基于度数枢纽的智能选择策略（默认）。

        算法：
        1. 从 Neo4j 中查出每个 Entity 节点的总度数 (入度+出度)
        2. 选出度数最高的 seed_count 个核心节点 (hub)
        3. 扩展这些核心节点的 1-hop 邻居
        4. 合并去重后按度数降序返回，LIMIT 到 max_nodes

        这保证了返回的子图：
        - 包含图中最核心的枢纽节点（高连接度）
        - 核心节点之间通过共享邻居有大量边连接
        - 形成结构上有意义的连通子图，而非碎片
        """
        effective_max = max_nodes or 400
        # 核心种子数：取 max_nodes 的 ~15%，至少 20 个，最多 100 个
        seed_count = max(20, min(100, effective_max // 6))

        node_where, params = self._group_filter("n", group_id)
        params["seed_count"] = seed_count
        params["total_limit"] = effective_max

        # 构造 group_id 过滤条件的多种变体
        group_match_clause = ""
        if group_id:
            group_match_clause = "WHERE n.group_id = $group_id"
        neighbor_group_clause = ""
        if group_id:
            neighbor_group_clause = "AND neighbor.group_id = $group_id"

        # 步骤 1+2: 找到度数最高的 seed 节点
        # 步骤 3: 扩展 1-hop 邻居
        # 步骤 4: 合并去重，按度数降序，LIMIT
        nodes = self.client.run_query(
            f"""
            // Step 1: 计算所有节点的度数，选出 Top seed
            MATCH (n:Entity)
            {group_match_clause}
            WITH n,
                 size([(n)-[:RELATES_TO]->() | 1]) +
                 size([()-[:RELATES_TO]->(n) | 1]) AS degree
            ORDER BY degree DESC
            LIMIT $seed_count
            WITH collect(n) AS seeds

            // Step 2: 扩展每个 seed 的 1-hop 邻居
            UNWIND seeds AS seed
            OPTIONAL MATCH (seed)-[:RELATES_TO]-(neighbor:Entity)
            WHERE neighbor IS NOT NULL {neighbor_group_clause}
            WITH seeds, collect(DISTINCT neighbor) AS neighbors

            // Step 3: 合并 seeds + neighbors，去重
            WITH [node IN seeds + neighbors | node] AS all_nodes
            UNWIND all_nodes AS n
            WITH DISTINCT n

            // Step 4: 重新计算度数用于排序，按度数降序
            WITH n,
                 size([(n)-[:RELATES_TO]->() | 1]) +
                 size([()-[:RELATES_TO]->(n) | 1]) AS degree
            ORDER BY degree DESC
            LIMIT $total_limit

            RETURN n.uuid AS id,
                   coalesce(n.name, n.uuid) AS name,
                   labels(n) AS labels,
                   n.group_id AS group_id,
                   n.summary AS summary,
                   properties(n) AS attributes
            """,
            params,
        )

        logger.info(
            "degree_hub selection: seed_count=%d, returned=%d nodes (limit=%d)",
            seed_count, len(nodes), effective_max,
        )
        return nodes

    # ------------------------------------------------------------------
    # 主加载方法
    # ------------------------------------------------------------------

    def load_graph(
        self,
        graph_id: str | None = None,
        group_id: str | None = None,
        max_nodes: int | None = None,
        max_edges: int | None = None,
        selection_mode: SelectionMode = "degree_hub",
    ) -> GraphData:
        effective_group = self.resolve_group_id(graph_id=graph_id, group_id=group_id)

        # --- 节点选择 ---
        if selection_mode == "degree_hub" and max_nodes is not None:
            nodes = self._select_nodes_degree_hub(effective_group, max_nodes)
        elif selection_mode == "random_sample":
            nodes = self._select_nodes_random(effective_group, max_nodes)
        else:
            # alphabetical 模式，或 degree_hub 无 limit 时回退全量加载
            nodes = self._select_nodes_alphabetical(effective_group, max_nodes)

        # --- 边加载 ---
        edge_where, edge_params = self._group_filter("e", effective_group)
        edge_limit_clause = "LIMIT $edge_limit" if max_edges is not None else ""
        if max_edges is not None:
            edge_params["edge_limit"] = max_edges

        edges = self.client.run_query(
            f"""
            MATCH (source:Entity)-[e:RELATES_TO]->(target:Entity)
            {edge_where}
            RETURN e.uuid AS id,
                   source.uuid AS source,
                   target.uuid AS target,
                   e.name AS name,
                   e.fact AS fact,
                   e.group_id AS group_id,
                   coalesce(e.weight, 1.0) AS weight,
                   properties(e) AS attributes
            ORDER BY e.uuid
            {edge_limit_clause}
            """,
            edge_params,
        )

        # --- 归一化 + 边一致性过滤 ---
        normalized_nodes = [
            {
                **node,
                "summary": self._normalize_value(node.get("summary")),
                "attributes": self._normalize_value(node.get("attributes", {})),
            }
            for node in nodes
        ]
        node_ids = {node["id"] for node in normalized_nodes}
        normalized_edges = [
            {
                **edge,
                "attributes": self._normalize_value(edge.get("attributes", {})),
                "weight": float(edge.get("weight") or 1.0),
            }
            for edge in edges
            if edge.get("source") in node_ids and edge.get("target") in node_ids
        ]

        logger.info(
            "load_graph: mode=%s, group=%s, nodes=%d, edges=%d (filtered from %d)",
            selection_mode, effective_group, len(normalized_nodes),
            len(normalized_edges), len(edges),
        )

        return GraphData(
            graph_id=effective_group or "default",
            nodes=[GraphNode(**node) for node in normalized_nodes],
            edges=[GraphEdge(**edge) for edge in normalized_edges],
        )

    def build_summary(self, graph: GraphData, top_nodes: list[NodeMetricItem]) -> GraphSummaryResponse:
        label_counter: Counter[str] = Counter()
        for node in graph.nodes:
            label_counter.update(node.labels or ["Entity"])

        return GraphSummaryResponse(
            graph_id=graph.graph_id,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
            labels=dict(label_counter.most_common()),
            top_nodes=top_nodes,
        )
