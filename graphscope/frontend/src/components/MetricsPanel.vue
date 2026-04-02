<script setup>
const props = defineProps({
  metrics: { type: Object, default: null },
  communities: { type: Array, default: () => [] },
})

function formatValue(value) {
  if (value === null || value === undefined) return '—'
  return typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 4 }) : value
}
</script>

<template>
  <section class="panel metrics-panel">
    <div class="panel-header">
      <h2>网络指标</h2>
      <p>面向结构分析和 GraphRAG 的全局视角</p>
    </div>

    <div v-if="metrics" class="metric-grid">
      <article class="metric-card">
        <span>节点数</span>
        <strong>{{ formatValue(metrics.node_count) }}</strong>
      </article>
      <article class="metric-card">
        <span>边数</span>
        <strong>{{ formatValue(metrics.edge_count) }}</strong>
      </article>
      <article class="metric-card">
        <span>网络密度</span>
        <strong>{{ formatValue(metrics.density) }}</strong>
      </article>
      <article class="metric-card">
        <span>平均度</span>
        <strong>{{ formatValue(metrics.average_degree) }}</strong>
      </article>
      <article class="metric-card">
        <span>平均聚类系数</span>
        <strong>{{ formatValue(metrics.average_clustering) }}</strong>
      </article>
      <article class="metric-card">
        <span>全局聚类系数 (Transitivity)</span>
        <strong>{{ formatValue(metrics.transitivity) }}</strong>
      </article>
      <article class="metric-card">
        <span>最大连通子图</span>
        <strong>{{ formatValue(metrics.largest_component_size) }}</strong>
      </article>
      <article class="metric-card">
        <span>连通分量数</span>
        <strong>{{ formatValue(metrics.connected_components) }}</strong>
      </article>
      <article class="metric-card">
        <span>平均最短路径</span>
        <strong>{{ formatValue(metrics.average_shortest_path_length) }}</strong>
      </article>
      <article class="metric-card">
        <span>网络直径</span>
        <strong>{{ formatValue(metrics.diameter) }}</strong>
      </article>
      <article class="metric-card">
        <span>桥边数量</span>
        <strong>{{ formatValue(metrics.bridge_edge_count) }}</strong>
      </article>
      <article class="metric-card">
        <span>同配系数 (Assortativity)</span>
        <strong>{{ formatValue(metrics.assortativity) }}</strong>
      </article>
      <article class="metric-card">
        <span>模块度 (Modularity)</span>
        <strong>{{ formatValue(metrics.modularity) }}</strong>
      </article>
      <article class="metric-card">
        <span>最大 K-Core 层数</span>
        <strong>{{ formatValue(metrics.max_core_number) }}</strong>
      </article>
    </div>

    <div class="community-block">
      <div class="sub-header">
        <h3>社区概览</h3>
        <span>{{ communities.length }} 个社区</span>
      </div>
      <div class="community-list">
        <article v-for="community in communities.slice(0, 4)" :key="community.community_id" class="community-item">
          <div>
            <strong>社区 {{ community.community_id }}</strong>
            <p>规模 {{ community.size }} · 密度 {{ formatValue(community.density) }}</p>
          </div>
          <small>{{ community.core_nodes.map((node) => node.name).join('、') || '暂无核心节点' }}</small>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  padding: 22px;
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(18px);
}

.panel-header h2,
.sub-header h3 {
  margin: 0;
  font-size: 1.05rem;
}

.panel-header p,
.sub-header span,
.community-item p,
.community-item small {
  margin: 4px 0 0;
  color: #93a4c3;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.metric-card {
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(30, 41, 59, 0.82), rgba(15, 23, 42, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.08);
}

.metric-card span {
  display: block;
  color: #8ea3c4;
  font-size: 0.84rem;
}

.metric-card strong {
  display: block;
  margin-top: 8px;
  font-size: 1.25rem;
}

.community-block {
  margin-top: 22px;
}

.sub-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.community-list {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.community-item {
  padding: 14px;
  border-radius: 16px;
  background: rgba(30, 41, 59, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.08);
}
</style>
