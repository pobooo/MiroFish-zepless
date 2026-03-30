from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.cache import TTLCache
from app.core.config import Settings, get_settings
from app.models.schemas import (
    CommunityResponse,
    GraphData,
    GraphMetricsResponse,
    GraphPathResponse,
    GraphSummaryResponse,
    GroupListResponse,
    HealthResponse,
    RAGContextRequest,
    RAGContextResponse,
    RankingResponse,
)
from app.services.analysis import GraphAnalysisService
from app.services.graph_loader import GraphLoaderService, SelectionMode
from app.services.neo4j_client import Neo4jClient, get_neo4j_client
from app.services.rag_support import GraphRAGSupportService

router = APIRouter()
analysis_service = GraphAnalysisService()
cache = TTLCache(ttl_seconds=get_settings().cache_ttl_seconds)


def get_loader(client: Neo4jClient = Depends(get_neo4j_client)) -> GraphLoaderService:
    return GraphLoaderService(client)


def get_rag_service() -> GraphRAGSupportService:
    return GraphRAGSupportService(analysis_service)


def _load_graph(
    loader: GraphLoaderService,
    graph_id: str | None,
    group_id: str | None,
    max_nodes: int | None = None,
    max_edges: int | None = None,
    selection_mode: SelectionMode = "degree_hub",
) -> GraphData:
    return loader.load_graph(
        graph_id=graph_id,
        group_id=group_id,
        max_nodes=max_nodes,
        max_edges=max_edges,
        selection_mode=selection_mode,
    )


@router.get("/health", response_model=HealthResponse)
def healthcheck(
    settings: Settings = Depends(get_settings),
    client: Neo4jClient = Depends(get_neo4j_client),
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        neo4j_connected=client.verify(),
        app_name=settings.app_name,
    )


@router.get("/groups", response_model=GroupListResponse)
def list_groups(
    loader: GraphLoaderService = Depends(get_loader),
) -> GroupListResponse:
    """列出 Neo4j 中所有可用的 MiroFish 项目（group_id），按节点数降序排列。"""
    return loader.list_groups()


@router.get("/graphs/data", response_model=GraphData)
def get_graph_data(
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    max_nodes: int = Query(default=400, ge=50, le=2000),
    max_edges: int = Query(default=800, ge=50, le=4000),
    selection_mode: SelectionMode = Query(default="degree_hub"),
    loader: GraphLoaderService = Depends(get_loader),
) -> GraphData:
    return _load_graph(
        loader, graph_id, group_id,
        max_nodes=max_nodes, max_edges=max_edges,
        selection_mode=selection_mode,
    )


@router.get("/graphs/metrics", response_model=GraphMetricsResponse)
def get_graph_metrics(
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    top_k: int = Query(default=10, ge=3, le=50),
    community_algorithm: str = Query(default="louvain"),
    use_cache: bool = True,
    loader: GraphLoaderService = Depends(get_loader),
) -> GraphMetricsResponse:
    cache_key = f"metrics:{graph_id}:{group_id}:{top_k}:{community_algorithm}"
    if use_cache and (cached := cache.get(cache_key)) is not None:
        return cached

    graph = _load_graph(loader, graph_id, group_id)
    result = analysis_service.analyze(graph, top_k=top_k, community_algorithm=community_algorithm)
    if use_cache:
        cache.set(cache_key, result)
    return result


@router.get("/graphs/summary", response_model=GraphSummaryResponse)
def get_graph_summary(
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    loader: GraphLoaderService = Depends(get_loader),
) -> GraphSummaryResponse:
    graph = _load_graph(loader, graph_id, group_id)
    metrics = analysis_service.analyze(graph, top_k=5)
    return loader.build_summary(graph, metrics.important_nodes[:5])


@router.get("/graphs/rankings", response_model=RankingResponse)
def get_rankings(
    metric: str = Query(default="pagerank"),
    top_k: int = Query(default=10, ge=3, le=50),
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    loader: GraphLoaderService = Depends(get_loader),
) -> RankingResponse:
    graph = _load_graph(loader, graph_id, group_id)
    result = analysis_service.analyze(graph, top_k=top_k)
    metric_items = result.rankings.get(metric, [])
    return RankingResponse(graph_id=result.graph_id, metric=metric, items=metric_items)


@router.get("/graphs/communities", response_model=CommunityResponse)
def get_communities(
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    algorithm: str = Query(default="louvain"),
    loader: GraphLoaderService = Depends(get_loader),
) -> CommunityResponse:
    graph = _load_graph(loader, graph_id, group_id)
    network = analysis_service.build_graph(graph)
    communities = analysis_service.detect_communities(network, algorithm=algorithm)
    return CommunityResponse(graph_id=graph.graph_id, algorithm=algorithm, communities=communities)


@router.get("/rag/important-nodes", response_model=RankingResponse)
def rag_important_nodes(
    metric: str = Query(default="pagerank"),
    top_k: int = Query(default=10, ge=3, le=50),
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    loader: GraphLoaderService = Depends(get_loader),
) -> RankingResponse:
    graph = _load_graph(loader, graph_id, group_id)
    metrics = analysis_service.analyze(graph, top_k=top_k)
    items = metrics.rankings.get(metric) or [
        item.model_copy(update={"metric": metric}) for item in metrics.important_nodes[:top_k]
    ]
    return RankingResponse(graph_id=graph.graph_id, metric=metric, items=items)


@router.post("/rag/context", response_model=RAGContextResponse)
def rag_context(
    request: RAGContextRequest,
    loader: GraphLoaderService = Depends(get_loader),
    rag_service: GraphRAGSupportService = Depends(get_rag_service),
) -> RAGContextResponse:
    cache_key = f"rag:{request.graph_id}:{request.group_id}:{request.strategy}:{request.max_nodes}:{request.query}"
    if cached := cache.get(cache_key):
        return cached
    graph = _load_graph(loader, request.graph_id, request.group_id)
    result = rag_service.build_context(graph, request)
    cache.set(cache_key, result)
    return result


@router.get("/rag/paths", response_model=GraphPathResponse)
def rag_paths(
    source: str,
    target: str,
    graph_id: str | None = Query(default=None),
    group_id: str | None = Query(default=None),
    max_depth: int = Query(default=4, ge=2, le=8),
    loader: GraphLoaderService = Depends(get_loader),
    rag_service: GraphRAGSupportService = Depends(get_rag_service),
) -> GraphPathResponse:
    graph = _load_graph(loader, graph_id, group_id)
    return rag_service.find_paths(graph, source, target, max_depth=max_depth)
