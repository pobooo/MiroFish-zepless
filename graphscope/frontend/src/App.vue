<script setup>
import { computed, onMounted, ref } from 'vue'
import { fetchGraphData, fetchGraphMetrics, fetchGroups, fetchHealth, fetchRagContext } from './api'
import BuildPanel from './components/BuildPanel.vue'
import ContextPanel from './components/ContextPanel.vue'
import EdgeDetailPanel from './components/EdgeDetailPanel.vue'
import GraphCanvas from './components/GraphCanvas.vue'
import MetricsPanel from './components/MetricsPanel.vue'
import NodeDetailPanel from './components/NodeDetailPanel.vue'
import RankingPanel from './components/RankingPanel.vue'

const activeTab = ref('analyze') // analyze | build

const health = ref(null)
const groups = ref([])
const groupId = ref('')
const topK = ref(10)
const metric = ref('pagerank')
const communityAlgorithm = ref('louvain')
const ragStrategy = ref('community_aware')
const ragQuery = ref('图谱中最关键的人物和桥接节点是谁？')
const selectionMode = ref('degree_hub')
const loading = ref(false)
const metricsLoading = ref(false)
const ragLoading = ref(false)
const error = ref('')

const graph = ref({ nodes: [], edges: [], graph_id: 'default' })
const metrics = ref(null)
const ragContext = ref(null)
const contextPanelRef = ref(null)
const selectedNodeId = ref(null)
const selectedEdge = ref(null)

const scoreMap = computed(() => {
  const items = metrics.value?.rankings?.[rankingView.value] || []
  return Object.fromEntries(items.map((item) => [item.node_id, item.score]))
})

const selectedNode = computed(() => {
  if (!selectedNodeId.value) return null
  // 优先从画布节点找（有完整 attributes / summary）
  const canvasNode = graph.value.nodes.find((n) => n.id === selectedNodeId.value)
  if (canvasNode) return canvasNode
  // 画布中没有 → 从排行数据构造轻量节点（至少能展示名称、类型、分数）
  for (const items of Object.values(metrics.value?.rankings || {})) {
    const hit = items.find((item) => item.node_id === selectedNodeId.value)
    if (hit) {
      return {
        id: hit.node_id,
        name: hit.name,
        labels: hit.labels || [],
        summary: '',
        attributes: {},
      }
    }
  }
  return null
})
const importantNodes = computed(() => metrics.value?.important_nodes || [])

const entityTypeFilter = ref('')
const rankingView = ref('pagerank')

// 指标描述，供用户参考
const metricDescriptions = {
  pagerank: { name: 'PageRank（影响力）', desc: '被"重要节点"指向的节点更重要。适合发现全局最有影响力的核心节点，如行业巨头。' },
  betweenness_centrality: { name: 'Betweenness（桥接力）', desc: '处于多个节点对之间最短路径上的程度。适合发现信息传播的关键枢纽和跨社区桥梁节点。' },
  degree_centrality: { name: 'Degree（连接数）', desc: '直接连接的邻居数量。适合发现局部最活跃的节点，简单直观但不考虑连接质量。' },
  closeness_centrality: { name: 'Closeness（接近度）', desc: '到其他所有节点的平均距离最短。适合发现信息扩散最快、位置最中心的节点。' },
  eigenvector_centrality: { name: 'Eigenvector（圈子质量）', desc: '连接到高分节点的节点得分更高。适合发现处于核心权力圈中的节点。' },
  katz_centrality: { name: 'Katz（间接影响力）', desc: '考虑所有路径（不只最短路径）的影响力，带衰减系数。发现间接影响力大的节点。' },
  harmonic_centrality: { name: 'Harmonic（调和接近度）', desc: 'Closeness 的改进版，处理非连通图更稳健。适合有孤立社区的图谱。' },
  clustering_coefficient: { name: 'Clustering（聚类系数）', desc: '节点邻居之间的互连程度（抱团系数）。高值节点处于紧密圈子中。' },
  core_number: { name: 'K-Core（核心层数）', desc: '节点所属的最大 k-core 层数。值越大说明越处于图谱的核心层，而非边缘。' },
  hits_hub: { name: 'HITS Hub（枢纽分）', desc: '指向大量权威节点的枢纽得分。适合发现信息分发中心。' },
  hits_authority: { name: 'HITS Authority（权威分）', desc: '被大量枢纽指向的权威得分。适合发现被广泛引用的权威节点。' },
}
const currentMetricDesc = computed(() => metricDescriptions[rankingView.value] || metricDescriptions.pagerank)

// 实体类型：从 Neo4j 标签提取（包含所有标签）
const entityTypes = computed(() => {
  const types = new Set()
  for (const node of graph.value.nodes) {
    for (const label of (node.labels || [])) {
      types.add(label)
    }
  }
  for (const node of importantNodes.value) {
    for (const label of (node.labels || [])) {
      types.add(label)
    }
  }
  return Array.from(types).sort()
})

// 统一排行数据：根据选择的视角返回不同数据源，先按类型过滤再取 Top K
const displayedRankingItems = computed(() => {
  let items = metrics.value?.rankings?.[rankingView.value] || []
  // 类型过滤
  if (entityTypeFilter.value) {
    items = items.filter((node) =>
      (node.labels || []).includes(entityTypeFilter.value)
    )
  }
  // 过滤后再截断 Top K
  return items.slice(0, topK.value)
})

function formatGroupLabel(g) {
  const stats = `${g.node_count}节点 ${g.edge_count}边`
  const labels = g.label_sample?.length ? g.label_sample.slice(0, 2).join(', ') : ''

  // 有项目名 → 直接用
  if (g.project_name) {
    return `📌 ${g.project_name} — ${stats}${labels ? ' · ' + labels : ''}`
  }

  // 无项目名 → 用 top_entities 做摘要
  const source = g.group_id.startsWith('graphscope_') ? 'GS' : 'MF'
  const shortId = g.group_id.replace('mirofish_', '').replace('graphscope_', '').slice(0, 6)
  const entities = g.top_entities?.length ? g.top_entities.join(', ') : shortId

  return `[${source}] ${entities} — ${stats}${labels ? ' · ' + labels : ''}`
}

async function refreshHealth() {
  try {
    const [h, g] = await Promise.all([fetchHealth(), fetchGroups()])
    health.value = h
    groups.value = g.groups || []
    // 如果还没有选过项目，自动选节点最多的那个
    if (!groupId.value && groups.value.length) {
      groupId.value = groups.value[0].group_id
    }
  } catch (err) {
    console.error(err)
  }
}

let metricsRequestId = 0

async function refresh() {
  loading.value = true
  error.value = ''
  selectedNodeId.value = null
  entityTypeFilter.value = ''
  rankingView.value = 'pagerank'
  metrics.value = null  // 立即清空旧指标，避免显示上一个项目的数据
  try {
    // 1. 先加载图数据（快，1-2秒）
    const graphData = await fetchGraphData(groupId.value || undefined, 400, 800, selectionMode.value)
    graph.value = graphData
    if (!groupId.value && graphData.graph_id && graphData.graph_id !== 'default') {
      groupId.value = graphData.graph_id
    }

  } catch (err) {
    error.value = err.message || '加载失败'
  } finally {
    loading.value = false
  }

  // 2. metrics 后台异步加载（慢，10-20秒），不阻塞 UI
  const currentRequestId = ++metricsRequestId
  metricsLoading.value = true
  fetchGraphMetrics(groupId.value || undefined, topK.value, communityAlgorithm.value)
    .then((data) => {
      // 竞态保护：只接受最新一次请求的结果
      if (currentRequestId === metricsRequestId) {
        metrics.value = data
      }
    })
    .catch((err) => { console.error('metrics load failed:', err) })
    .finally(() => {
      if (currentRequestId === metricsRequestId) {
        metricsLoading.value = false
      }
    })
}

async function generateContext() {
  ragLoading.value = true
  error.value = ''
  try {
    ragContext.value = await fetchRagContext({
      query: ragQuery.value,
      group_id: groupId.value || null,
      strategy: ragStrategy.value,
      max_nodes: Math.min(topK.value + 5, 20),
    })
  } catch (err) {
    error.value = err.message || '上下文生成失败'
  } finally {
    ragLoading.value = false
    // 主动刷新迷你图谱
    setTimeout(() => contextPanelRef.value?.refresh(), 100)
  }
}

// ---- 侧栏节点详情辅助 ----
const SYSTEM_LABELS = new Set(['Entity', 'Node', 'Episodic'])
const HIDDEN_ATTRS = new Set([
  'uuid', 'name', 'group_id', 'summary', 'created_at', 'embedding',
  'name_embedding', 'labels', 'source_description',
])
const NODE_TYPE_COLORS = {
  Person: '#60a5fa', Organization: '#f472b6', Company: '#34d399',
  University: '#fbbf24', MediaOutlet: '#a78bfa', GovernmentAgency: '#fb923c',
  TechCompany: '#2dd4bf', Researcher: '#f87171', AIModel: '#818cf8',
  Startup: '#4ade80', GameDeveloper: '#e879f9', AIProduct: '#38bdf8',
}

function getNodeEntityType(node) {
  if (!node) return 'Entity'
  for (const lbl of (node.labels || [])) {
    if (!SYSTEM_LABELS.has(lbl)) return lbl
  }
  return 'Entity'
}

function getNodeTypeColor(node) {
  return NODE_TYPE_COLORS[getNodeEntityType(node)] || '#94a3b8'
}

const nodeScore = computed(() => {
  if (!selectedNodeId.value) return null
  return scoreMap.value[selectedNodeId.value] ?? null
})

const nodeExtraProps = computed(() => {
  if (!selectedNode.value) return []
  const attrs = selectedNode.value.attributes || {}
  return Object.entries(attrs)
    .filter(([k]) => !HIDDEN_ATTRS.has(k))
    .map(([k, v]) => ({ key: k, value: typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? '') }))
    .filter((item) => item.value !== '' && item.value !== 'null')
})

function selectNode(nodeId) {
  selectedNodeId.value = nodeId
  if (nodeId) selectedEdge.value = null
}

function selectEdge(edge) {
  selectedEdge.value = edge
  if (edge) selectedNodeId.value = null
}

async function onBuildComplete(result) {
  // 构建完成后切换到分析页并刷新
  if (result?.group_id) {
    groupId.value = result.group_id
  }
  activeTab.value = 'analyze'
  await refreshHealth()
  await refresh()
}

onMounted(async () => {
  await refreshHealth()
  await refresh()
  await generateContext()
})
</script>

<template>
  <main class="app-shell">
    <header class="hero">
      <div>
        <p class="eyebrow">Graph Analytics + GraphRAG Support</p>
        <h1>GraphScope</h1>
        <p class="hero-copy">
          连接 Graphiti / Neo4j 图谱，计算复杂网络指标，识别关键节点，并输出可直接供 Agent 使用的结构化上下文。
        </p>
      </div>
      <div class="hero-status">
        <div>
          <span>服务状态</span>
          <strong>{{ health?.status || 'loading' }}</strong>
        </div>
        <div>
          <span>Neo4j</span>
          <strong :class="health?.neo4j_connected ? 'ok' : 'bad'">
            {{ health?.neo4j_connected ? 'connected' : 'disconnected' }}
          </strong>
        </div>
      </div>
    </header>

    <!-- Tab 切换 -->
    <nav class="tab-bar">
      <button :class="{ active: activeTab === 'build' }" @click="activeTab = 'build'">
        📦 图谱构建
      </button>
      <button :class="{ active: activeTab === 'analyze' }" @click="activeTab = 'analyze'">
        📊 图谱分析
      </button>
    </nav>

    <!-- 构建面板（v-show 保持状态） -->
    <section v-show="activeTab === 'build'" class="build-section">
      <BuildPanel :groups="groups" @build-complete="onBuildComplete" />
    </section>

    <!-- 分析面板（原有内容） -->
    <template v-if="activeTab === 'analyze'">
    <section class="toolbar">
      <label>
        <span>项目 (Group)</span>
        <select v-model="groupId">
          <option value="">自动选取（节点最多）</option>
          <option v-for="g in groups" :key="g.group_id" :value="g.group_id">
            {{ formatGroupLabel(g) }}
          </option>
        </select>
      </label>
      <label>
        <span>节点选取</span>
        <select v-model="selectionMode">
          <option value="degree_hub">度数枢纽 (Hub + 邻居)</option>
          <option value="alphabetical">字母排序</option>
          <option value="random_sample">随机采样</option>
        </select>
      </label>
      <label>
        <span>社区算法</span>
        <select v-model="communityAlgorithm">
          <option value="louvain">Louvain</option>
          <option value="label_propagation">Label Propagation</option>
        </select>
      </label>
      <label>
        <span>Top K</span>
        <input v-model.number="topK" type="number" min="3" max="20" />
      </label>
      <button class="primary" :disabled="loading" @click="refresh">
        {{ loading ? '加载图谱…' : metricsLoading ? '指标计算中…' : '刷新图谱' }}
      </button>
    </section>

    <section v-if="error" class="error-banner">{{ error }}</section>

    <section class="dashboard-grid">
      <div class="main-column">
        <div class="graph-wrapper">
          <GraphCanvas
            :nodes="graph.nodes"
            :edges="graph.edges"
            :score-map="scoreMap"
            :selected-node-id="selectedNodeId"
            :selected-edge-id="selectedEdge?.id || null"
            @select-node="selectNode"
            @select-edge="selectEdge"
          />
          <NodeDetailPanel
            :node="selectedNode"
            @close="selectedNodeId = null"
          />
          <EdgeDetailPanel
            :edge="selectedEdge"
            :nodes="graph.nodes"
            @close="selectedEdge = null"
          />
        </div>
      </div>

      <div class="side-column">
        <div v-if="metricsLoading && !metrics" class="panel metrics-loading-hint">
          <p>⏳ 网络指标计算中…（约 10-20 秒）</p>
        </div>
        <MetricsPanel
          v-if="metrics"
          :metrics="metrics?.global_metrics"
          :communities="metrics?.communities || []"
        />
      </div>
    </section>

    <!-- 排行 + 详情：独立全宽区域，左详情 右排行 -->
    <section class="ranking-section">
      <div class="ranking-section-header">
        <div class="type-filter-bar">
          <div class="type-filter-left">
            <span class="type-filter-label">节点排行</span>
            <span class="type-filter-sub">点击节点查看详情</span>
          </div>
          <div class="type-filter-right">
            <select v-model="rankingView" class="type-filter-select">
              <option value="pagerank">PageRank（影响力）</option>
              <option value="betweenness_centrality">Betweenness（桥接力）</option>
              <option value="degree_centrality">Degree（连接数）</option>
              <option value="closeness_centrality">Closeness（接近度）</option>
              <option value="eigenvector_centrality">Eigenvector（圈子质量）</option>
              <option value="katz_centrality">Katz（间接影响力）</option>
              <option value="harmonic_centrality">Harmonic（调和接近度）</option>
              <option value="clustering_coefficient">Clustering（聚类系数）</option>
              <option value="core_number">K-Core（核心层数）</option>
              <option value="hits_hub">HITS Hub（枢纽分）</option>
              <option value="hits_authority">HITS Authority（权威分）</option>
            </select>
            <select v-model="entityTypeFilter" class="type-filter-select">
              <option value="">全部类型</option>
              <option v-for="t in entityTypes" :key="t" :value="t">{{ t }}</option>
            </select>
            <span class="type-filter-badge">Top {{ displayedRankingItems.length }}</span>
          </div>
        </div>
        <div class="metric-desc-bar metric-desc-bar-full">
          <span class="metric-desc-icon">💡</span>
          <span class="metric-desc-text">{{ currentMetricDesc.desc }}</span>
        </div>
      </div>

      <div v-if="metricsLoading && !importantNodes.length" class="panel metrics-loading-hint">
        <p>⏳ 正在计算网络指标…</p>
      </div>
      <div v-else class="ranking-detail-grid">
        <!-- 左：节点详情 -->
        <div class="ranking-detail-left">
          <Transition name="detail-fade" mode="out-in">
            <div v-if="selectedNode" :key="selectedNode.id" class="side-node-detail">
              <div class="side-detail-header">
                <h3>节点详情</h3>
                <span class="side-type-badge" :style="{ background: getNodeTypeColor(selectedNode) }">
                  {{ getNodeEntityType(selectedNode) }}
                </span>
                <button class="side-close-btn" @click="selectedNodeId = null">✕</button>
              </div>
              <div class="side-detail-body">
                <div v-if="selectedNode.name" class="side-info-row">
                  <span class="side-info-label">名称</span>
                  <span class="side-info-value">{{ selectedNode.name }}</span>
                </div>
                <div v-if="selectedNode.id" class="side-info-row">
                  <span class="side-info-label">UUID</span>
                  <span class="side-info-value uuid">{{ selectedNode.id }}</span>
                </div>
                <div v-if="selectedNode.attributes?.created_at" class="side-info-row">
                  <span class="side-info-label">创建</span>
                  <span class="side-info-value">{{ new Date(selectedNode.attributes.created_at).toLocaleString() }}</span>
                </div>
                <div v-if="nodeScore != null" class="side-info-row">
                  <span class="side-info-label">{{ currentMetricDesc.name }}</span>
                  <span class="side-info-value score-val">{{ Number(nodeScore).toLocaleString(undefined, { maximumFractionDigits: 6 }) }}</span>
                </div>
                <div v-if="selectedNode.summary" class="side-summary">
                  <span class="side-info-label">摘要</span>
                  <p>{{ selectedNode.summary }}</p>
                </div>
                <div v-if="nodeExtraProps.length" class="side-props">
                  <span class="side-info-label">属性</span>
                  <div v-for="p in nodeExtraProps" :key="p.key" class="side-prop-row">
                    <span class="side-prop-key">{{ p.key }}</span>
                    <span class="side-prop-val">{{ p.value }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="side-node-detail side-empty-hint">
              <p>👈 点击右侧排行中的节点查看详情</p>
            </div>
          </Transition>
        </div>
        <!-- 右：排行列表 -->
        <div class="ranking-detail-right">
          <RankingPanel
            hide-title
            :items="displayedRankingItems"
            :selected-node-id="selectedNodeId"
            @select-node="selectNode"
          />
        </div>
      </div>
    </section>

    <section class="rag-section">
      <div class="rag-toolbar">
        <label class="rag-query">
          <span>GraphRAG 查询</span>
          <textarea v-model="ragQuery" rows="3" placeholder="例如：这个图谱中最关键的人物和跨社区桥节点是谁？" />
        </label>
        <div class="rag-controls">
          <label>
            <span>上下文策略</span>
            <select v-model="ragStrategy">
              <option value="community_aware">community_aware</option>
              <option value="centrality_aware">centrality_aware</option>
              <option value="path_aware">path_aware</option>
            </select>
          </label>
          <button class="primary" :disabled="ragLoading" @click="generateContext">
            {{ ragLoading ? '生成中…' : '生成 GraphRAG 上下文' }}
          </button>
        </div>
      </div>

      <ContextPanel ref="contextPanelRef" :context="ragContext" :loading="ragLoading" />
    </section>
    </template>
  </main>
</template>

<style scoped>
:global(body) {
  margin: 0;
  min-width: 1280px;
  background:
    radial-gradient(circle at top, rgba(59, 130, 246, 0.2), transparent 30%),
    linear-gradient(180deg, #020617 0%, #07111f 100%);
  color: #f8fafc;
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

:global(*) {
  box-sizing: border-box;
}

.app-shell {
  padding: 32px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 24px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #93c5fd;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.74rem;
}

h1 {
  margin: 0;
  font-size: 3rem;
  line-height: 1;
}

.hero-copy {
  max-width: 780px;
  margin-top: 14px;
  color: #94a3b8;
  line-height: 1.7;
}

.hero-status {
  display: flex;
  gap: 16px;
}

.hero-status > div,
.toolbar,
.rag-toolbar {
  padding: 18px 20px;
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.14);
  backdrop-filter: blur(18px);
}

.hero-status span,
.toolbar span,
.rag-toolbar span {
  display: block;
  color: #93a4c3;
  font-size: 0.85rem;
}

.hero-status strong {
  display: block;
  margin-top: 6px;
  font-size: 1rem;
}

.ok { color: #86efac; }
.bad { color: #fca5a5; }

.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
}

.tab-bar button {
  width: auto;
  margin: 0;
  padding: 10px 24px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.6);
  color: #94a3b8;
  font: inherit;
  font-size: 0.92rem;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-bar button.active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.3), rgba(124, 58, 237, 0.3));
  border-color: rgba(59, 130, 246, 0.4);
  color: #f1f5f9;
  font-weight: 600;
}

.tab-bar button:hover:not(.active) {
  background: rgba(15, 23, 42, 0.85);
  color: #cbd5e1;
}

.build-section {
  max-width: 960px;
}

.toolbar {
  display: grid;
  grid-template-columns: 2.4fr 1fr 1fr 0.6fr auto;
  gap: 14px;
  margin-bottom: 24px;
  align-items: end;
}

label {
  display: block;
}

input,
select,
textarea,
button {
  width: 100%;
  margin-top: 8px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.86);
  color: #f8fafc;
  font: inherit;
}

textarea {
  resize: vertical;
}

button {
  cursor: pointer;
}

button.primary {
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  border: none;
  box-shadow: 0 16px 32px rgba(59, 130, 246, 0.2);
}

button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.important-nodes-panel {
  display: grid;
  gap: 0;
}

.type-filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 20px;
  border-radius: 18px 18px 0 0;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-bottom: none;
}

.type-filter-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.type-filter-label {
  color: #f1f5f9;
  font-size: 1.02rem;
  font-weight: 600;
  white-space: nowrap;
}

.type-filter-sub {
  color: #64748b;
  font-size: 0.78rem;
}

.type-filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.type-filter-select {
  width: auto;
  min-width: 120px;
  margin: 0;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 0.84rem;
}

.type-filter-badge {
  display: inline-flex;
  align-items: center;
  height: fit-content;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.16);
  color: #bfdbfe;
  font-size: 0.82rem;
  white-space: nowrap;
}

.type-filter-hint {
  color: #64748b;
  font-size: 0.82rem;
  font-style: italic;
}

.metric-desc-bar {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 20px;
  background: rgba(59, 130, 246, 0.06);
  border-left: 1px solid rgba(148, 163, 184, 0.14);
  border-right: 1px solid rgba(148, 163, 184, 0.14);
}

.metric-desc-icon {
  flex-shrink: 0;
  font-size: 0.82rem;
  line-height: 1.5;
}

.metric-desc-text {
  color: #94a3b8;
  font-size: 0.8rem;
  line-height: 1.5;
}

.error-banner {
  margin-bottom: 20px;
  padding: 14px 18px;
  border-radius: 18px;
  background: rgba(127, 29, 29, 0.35);
  border: 1px solid rgba(248, 113, 113, 0.35);
  color: #fecaca;
}

.metrics-loading-hint {
  padding: 22px;
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.15);
  backdrop-filter: blur(18px);
  text-align: center;
  color: #93a4c3;
}

.metrics-loading-hint p {
  margin: 0;
  font-size: 0.95rem;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1.7fr 0.95fr;
  gap: 24px;
  align-items: start;
}

.main-column,
.side-column,
.rag-section {
  display: grid;
  gap: 24px;
}

.graph-wrapper {
  position: relative;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
  color: #cbd5e1;
}

.rag-section {
  margin-top: 24px;
}

.rag-toolbar {
  display: grid;
  grid-template-columns: 1.8fr 0.9fr;
  gap: 18px;
}

.rag-controls {
  display: grid;
  gap: 14px;
  align-content: start;
}

/* ---- 排行 + 详情独立区域 ---- */
.ranking-section {
  margin-top: 24px;
}

.ranking-section-header {
  display: grid;
  gap: 0;
}

.ranking-section-header .type-filter-bar {
  border-radius: 18px 18px 0 0;
}

.metric-desc-bar-full {
  border-radius: 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.ranking-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr;
  gap: 0;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-top: none;
  border-radius: 0 0 24px 24px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.78);
}

.ranking-detail-left {
  border-right: 1px solid rgba(148, 163, 184, 0.1);
  min-height: 300px;
  display: flex;
  align-items: stretch;
}

.ranking-detail-left > * {
  width: 100%;
}

.ranking-detail-left .side-node-detail {
  border-radius: 0;
  border: none;
  background: transparent;
}

.ranking-detail-left .side-empty-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  font-size: 0.88rem;
}

.ranking-detail-left .side-empty-hint p {
  margin: 0;
}

.ranking-detail-right {
  max-height: 600px;
  overflow-y: auto;
}

.ranking-detail-right::-webkit-scrollbar {
  width: 4px;
}

.ranking-detail-right::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2);
  border-radius: 4px;
}

.ranking-detail-right .ranking-panel {
  border-radius: 0;
  border: none;
}

/* ---- 侧栏节点详情 ---- */
.side-node-detail {
  border-radius: 20px;
  background: rgba(15, 23, 42, 0.82);
  border: 1px solid rgba(96, 165, 250, 0.25);
  backdrop-filter: blur(18px);
  overflow: hidden;
}

.side-detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}

.side-detail-header h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: #f1f5f9;
}

.side-type-badge {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}

.side-close-btn {
  margin-left: auto;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: rgba(148, 163, 184, 0.12);
  color: #94a3b8;
  font-size: 0.78rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.side-close-btn:hover {
  background: rgba(148, 163, 184, 0.22);
  color: #f1f5f9;
}

.side-detail-body {
  padding: 14px 18px;
  display: grid;
  gap: 10px;
}

.side-info-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.side-info-label {
  flex-shrink: 0;
  min-width: 52px;
  color: #64748b;
  font-size: 0.78rem;
  font-weight: 500;
}

.side-info-value {
  color: #e2e8f0;
  font-size: 0.84rem;
  word-break: break-all;
}

.side-info-value.uuid {
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 0.72rem;
  color: #94a3b8;
}

.side-info-value.score-val {
  font-weight: 700;
  color: #60a5fa;
}

.side-summary {
  display: grid;
  gap: 4px;
}

.side-summary p {
  margin: 0;
  color: #cbd5e1;
  font-size: 0.82rem;
  line-height: 1.65;
}

.side-props {
  display: grid;
  gap: 6px;
}

.side-prop-row {
  display: flex;
  gap: 8px;
  padding-left: 52px;
}

.side-prop-key {
  flex-shrink: 0;
  font-family: 'SF Mono', Menlo, monospace;
  font-size: 0.76rem;
  color: #a78bfa;
}

.side-prop-val {
  color: #cbd5e1;
  font-size: 0.8rem;
  word-break: break-word;
}

/* Transition */
.detail-fade-enter-active,
.detail-fade-leave-active {
  transition: all 0.25s ease;
}

.detail-fade-enter-from,
.detail-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (max-width: 1440px) {
  :global(body) {
    min-width: 0;
  }

  .toolbar,
  .dashboard-grid,
  .rag-toolbar,
  .hero {
    grid-template-columns: 1fr;
    display: grid;
  }
}
</style>
