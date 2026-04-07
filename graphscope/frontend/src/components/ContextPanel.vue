<script setup>
import * as d3 from 'd3'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  context: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const panelRef = ref(null)
let simulation = null

const SYSTEM_LABELS = new Set(['Entity', 'Node', 'Episodic'])
const COLORS = [
  '#60a5fa', '#f472b6', '#34d399', '#fbbf24', '#a78bfa',
  '#fb923c', '#2dd4bf', '#f87171', '#818cf8', '#4ade80',
]

function getNodeType(node) {
  for (const lbl of (node.labels || [])) {
    if (!SYSTEM_LABELS.has(lbl)) return lbl
  }
  return 'Entity'
}

function renderMiniGraph() {
  if (!panelRef.value) return
  const container = panelRef.value.querySelector('.mini-graph-container')
  if (!container || !props.context?.nodes?.length) return

  // 彻底清理
  if (simulation) { simulation.stop(); simulation = null }
  d3.select(container).selectAll('*').remove()

  const width = container.clientWidth || 600
  const height = 360

  const svg = d3.select(container)
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('width', '100%')
    .attr('height', height)

  const zoomLayer = svg.append('g')
  svg.call(
    d3.zoom().scaleExtent([0.3, 4]).on('zoom', (event) => {
      zoomLayer.attr('transform', event.transform)
    }),
  )

  // 建立颜色映射
  const types = [...new Set(props.context.nodes.map(getNodeType))]
  const colorMap = {}
  types.forEach((t, i) => { colorMap[t] = COLORS[i % COLORS.length] })

  const nodes = props.context.nodes.map((n) => ({ ...n }))
  const nodeIds = new Set(nodes.map((n) => n.id))
  const edges = (props.context.edges || [])
    .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map((e) => ({ ...e }))

  // 边
  const link = zoomLayer.append('g')
    .selectAll('line')
    .data(edges)
    .join('line')
    .attr('stroke', 'rgba(124, 145, 186, 0.45)')
    .attr('stroke-width', 1.2)

  // 边标签
  const linkLabel = zoomLayer.append('g')
    .selectAll('text')
    .data(edges)
    .join('text')
    .text((d) => d.name || '')
    .attr('fill', 'rgba(148, 163, 184, 0.7)')
    .attr('font-size', 8)
    .attr('text-anchor', 'middle')
    .attr('pointer-events', 'none')

  // 节点组
  const node = zoomLayer.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .style('cursor', 'grab')

  node.append('circle')
    .attr('r', 10)
    .attr('fill', (d) => colorMap[getNodeType(d)] || '#94a3b8')
    .attr('stroke', '#0f172a')
    .attr('stroke-width', 1.2)
    .attr('opacity', 0.92)

  node.append('text')
    .text((d) => d.name)
    .attr('dx', 14)
    .attr('dy', 4)
    .attr('fill', '#e2e8f0')
    .attr('font-size', 10)
    .attr('pointer-events', 'none')

  node.append('title')
    .text((d) => `${d.name}\n类型: ${getNodeType(d)}${d.summary ? '\n' + d.summary.slice(0, 100) : ''}`)

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id((d) => d.id).distance(80).strength(0.3))
    .force('charge', d3.forceManyBody().strength(-180))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(22))
    .on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y)

      linkLabel
        .attr('x', (d) => (d.source.x + d.target.x) / 2)
        .attr('y', (d) => (d.source.y + d.target.y) / 2 - 4)

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

  // 节点拖拽
  node.call(
    d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.1).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
      }),
  )

  // 图例
  const legendGroup = svg.append('g')
    .attr('transform', 'translate(12, 12)')

  types.forEach((t, i) => {
    const g = legendGroup.append('g')
      .attr('transform', `translate(0, ${i * 18})`)
    g.append('circle')
      .attr('r', 5)
      .attr('fill', colorMap[t])
      .attr('opacity', 0.9)
    g.append('text')
      .text(t)
      .attr('x', 12)
      .attr('y', 4)
      .attr('fill', '#94a3b8')
      .attr('font-size', 10)
  })
}

// 等待 DOM 就绪后渲染
function scheduleRender() {
  if (simulation) { simulation.stop(); simulation = null }
  let attempts = 0
  const tryRender = () => {
    const container = panelRef.value?.querySelector('.mini-graph-container')
    if (container) {
      renderMiniGraph()
    } else if (attempts < 10) {
      attempts++
      setTimeout(tryRender, 50)
    }
  }
  setTimeout(tryRender, 30)
}

// 监听 loading 从 true 变 false（说明新数据刚到）
watch(() => props.loading, (newVal, oldVal) => {
  if (oldVal === true && newVal === false && props.context?.nodes?.length) {
    scheduleRender()
  }
})

// 初始加载时如果已有数据
onMounted(() => {
  if (props.context?.nodes?.length && !props.loading) {
    scheduleRender()
  }
})

onBeforeUnmount(() => {
  if (simulation) { simulation.stop(); simulation = null }
})

// 暴露 refresh 方法，供父组件在数据更新后主动调用
defineExpose({ refresh: scheduleRender })
</script>

<template>
  <section ref="panelRef" class="panel context-panel">
    <div class="panel-header">
      <h2>GraphRAG 上下文</h2>
      <p>面向 Agent / 报告生成的结构化上下文输出</p>
    </div>

    <div v-if="loading" class="placeholder">正在生成结构感知上下文…</div>
    <div v-else-if="context" class="context-body">
      <!-- 迷你图谱可视化 -->
      <div v-if="context.nodes?.length" class="mini-graph-section">
        <div class="section-header">
          <h3>上下文子图</h3>
          <span class="stats-badge">{{ context.nodes.length }} 节点 · {{ context.edges?.length || 0 }} 边</span>
        </div>
        <div class="mini-graph-container" />
      </div>

      <!-- 摘要 -->
      <div class="summary-section">
        <h3>摘要</h3>
        <pre>{{ context.summary }}</pre>
      </div>

      <!-- 引用线索 -->
      <div class="citation-list" v-if="context.citations?.length">
        <h3>引用线索</h3>
        <ul>
          <li v-for="(item, index) in context.citations" :key="index">{{ item }}</li>
        </ul>
      </div>
    </div>
    <div v-else class="placeholder">输入查询后可生成可直接喂给 LLM 的图上下文。</div>
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

.panel-header h2 {
  margin: 0;
  font-size: 1.05rem;
}

.panel-header p,
.placeholder,
li {
  color: #93a4c3;
}

.context-body {
  margin-top: 18px;
  display: grid;
  gap: 20px;
}

/* 迷你图谱 */
.mini-graph-section {
  border-radius: 18px;
  background:
    radial-gradient(circle at top, rgba(59, 130, 246, 0.1), transparent 40%),
    rgba(8, 15, 29, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.12);
  overflow: hidden;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
}

.section-header h3 {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 600;
  color: #e2e8f0;
}

.stats-badge {
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.15);
  color: #93c5fd;
  font-size: 0.78rem;
}

.mini-graph-container {
  width: 100%;
  height: 360px;
}

/* 摘要 & 引用 */
.summary-section h3,
.citation-list h3 {
  margin: 0 0 10px;
  font-size: 0.92rem;
  font-weight: 600;
  color: #e2e8f0;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
  font-family: inherit;
  color: #dbeafe;
}

ul {
  margin: 0;
  padding-left: 18px;
}

li {
  padding: 3px 0;
  line-height: 1.5;
}
</style>
