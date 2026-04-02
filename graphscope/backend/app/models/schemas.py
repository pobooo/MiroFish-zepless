from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    name: str
    labels: list[str] = Field(default_factory=list)
    group_id: str | None = None
    summary: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    name: str | None = None
    fact: str | None = None
    group_id: str | None = None
    weight: float = 1.0
    attributes: dict[str, Any] = Field(default_factory=dict)


class GraphData(BaseModel):
    graph_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GlobalMetrics(BaseModel):
    node_count: int
    edge_count: int
    density: float
    average_degree: float
    average_clustering: float
    connected_components: int
    largest_component_size: int
    average_shortest_path_length: float | None = None
    diameter: int | None = None
    bridge_edge_count: int = 0
    transitivity: float = 0
    assortativity: float | None = None
    modularity: float | None = None
    max_core_number: int = 0


class NodeMetricItem(BaseModel):
    node_id: str
    name: str
    score: float
    metric: str
    group_id: str | None = None
    labels: list[str] = Field(default_factory=list)


class CommunityItem(BaseModel):
    community_id: int
    size: int
    density: float
    core_nodes: list[NodeMetricItem] = Field(default_factory=list)
    member_node_ids: list[str] = Field(default_factory=list)


class ImportantNodeItem(NodeMetricItem):
    reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class GraphMetricsResponse(BaseModel):
    graph_id: str
    global_metrics: GlobalMetrics
    rankings: dict[str, list[NodeMetricItem]] = Field(default_factory=dict)
    communities: list[CommunityItem] = Field(default_factory=list)
    important_nodes: list[ImportantNodeItem] = Field(default_factory=list)


class GraphSummaryResponse(BaseModel):
    graph_id: str
    node_count: int
    edge_count: int
    labels: dict[str, int] = Field(default_factory=dict)
    top_nodes: list[NodeMetricItem] = Field(default_factory=list)


class RankingResponse(BaseModel):
    graph_id: str
    metric: str
    items: list[NodeMetricItem] = Field(default_factory=list)


class CommunityResponse(BaseModel):
    graph_id: str
    algorithm: Literal["louvain", "label_propagation"]
    communities: list[CommunityItem] = Field(default_factory=list)


class RAGContextRequest(BaseModel):
    query: str
    graph_id: str | None = None
    group_id: str | None = None
    strategy: Literal["centrality_aware", "community_aware", "path_aware"] = "community_aware"
    max_nodes: int = Field(default=15, ge=3, le=50)
    max_paths: int = Field(default=5, ge=1, le=20)


class RAGContextResponse(BaseModel):
    graph_id: str
    strategy: str
    summary: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class GraphPathResponse(BaseModel):
    graph_id: str
    source_node_id: str
    target_node_id: str
    paths: list[list[str]] = Field(default_factory=list)


class GroupInfo(BaseModel):
    """单个 group_id（项目）的概要信息"""
    group_id: str
    project_name: str | None = None
    node_count: int
    edge_count: int
    label_sample: list[str] = Field(default_factory=list, description="前几个出现频次最高的标签")
    top_entities: list[str] = Field(default_factory=list, description="度数最高的几个实体名称，用作项目概览")


class GroupListResponse(BaseModel):
    """所有可用 group_id 列表"""
    groups: list[GroupInfo] = Field(default_factory=list)
    total: int = 0


class HealthResponse(BaseModel):
    status: str
    neo4j_connected: bool
    app_name: str


# ============== 图谱构建相关 ==============


class OntologyRequest(BaseModel):
    """本体生成请求"""
    texts: list[str] = Field(description="文档文本列表")
    requirement: str = Field(default="请分析文本内容，自动设计实体和关系类型", description="分析需求描述")
    additional_context: str | None = None


class OntologyResponse(BaseModel):
    """本体生成响应"""
    entity_types: list[dict[str, Any]] = Field(default_factory=list)
    edge_types: list[dict[str, Any]] = Field(default_factory=list)
    analysis_summary: str = ""


class BuildRequest(BaseModel):
    """图谱构建请求"""
    text: str = Field(description="要构建图谱的文本")
    ontology: dict[str, Any] = Field(description="本体定义（entity_types + edge_types）")
    graph_name: str = Field(default="GraphScope Graph", description="图谱名称")
    chunk_size: int = Field(default=500, ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=200)


class BuildTaskResponse(BaseModel):
    """图谱构建任务响应"""
    task_id: str
    status: str
    progress: int = 0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    """文件上传响应"""
    files: list[dict[str, str]] = Field(default_factory=list, description="上传的文件信息列表")
    texts: list[str] = Field(default_factory=list, description="提取的文本列表")
    total_chars: int = 0
