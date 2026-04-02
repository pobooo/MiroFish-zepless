<script setup>
import * as d3 from 'd3'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  scoreMap: { type: Object, default: () => ({}) },
  selectedNodeId: { type: String, default: null },
  selectedEdgeId: { type: String, default: null },
})

const emit = defineEmits(['select-node', 'select-edge'])

const containerRef = ref(null)
let simulation

// ============== 配色 & 形状 ==============

// 20 种高辨识度颜色（比 Tableau10 多一倍覆盖面）
const TYPE_COLORS = [
  '#60a5fa', // blue
  '#f472b6', // pink
  '#34d399', // emerald
  '#fbbf24', // amber
  '#a78bfa', // violet
  '#fb923c', // orange
  '#2dd4bf', // teal
  '#f87171', // red
  '#818cf8', // indigo
  '#4ade80', // green
  '#e879f9', // fuchsia
  '#38bdf8', // sky
  '#facc15', // yellow
  '#c084fc', // purple
  '#fb7185', // rose
  '#22d3ee', // cyan
  '#a3e635', // lime
  '#f97316', // orange-dark
  '#94a3b8', // slate
  '#e2e8f0', // light
]

// 提取所有出现的实体类型（去掉 Entity/Node/Episodic 等系统标签）
const SYSTEM_LABELS = new Set(['Entity', 'Node', 'Episodic'])
const entityTypes = computed(() => {
  const types = new Set()
  for (const node of props.nodes) {
    for (const lbl of (node.labels || [])) {
      if (!SYSTEM_LABELS.has(lbl)) types.add(lbl)
    }
  }
  return Array.from(types).sort()
})

// 颜色映射：类型名 → 颜色
const colorMap = computed(() => {
  const map = {}
  entityTypes.value.forEach((t, i) => {
    map[t] = TYPE_COLORS[i % TYPE_COLORS.length]
  })
  return map
})

function getNodeType(node) {
  for (const lbl of (node.labels || [])) {
    if (!SYSTEM_LABELS.has(lbl)) return lbl
  }
  return 'Entity'
}

function getNodeColor(node) {
  return colorMap.value[getNodeType(node)] || '#94a3b8'
}

// 图例数据
const legend = computed(() =>
  entityTypes.value.map((t, i) => ({
    type: t,
    color: TYPE_COLORS[i % TYPE_COLORS.length],
  }))
)

// 图例折叠状态
const legendCollapsed = ref(false)

// ============== 节点尺寸 ==============

const sizedNodes = computed(() => {
  return props.nodes.map((node) => ({
    ...node,
    visualSize: 12,
  }))
})

// ============== 渲染 ==============

function render() {
  if (!containerRef.value) return
  const container = containerRef.value.querySelector('.canvas-area')
  if (!container) return

  const width = container.clientWidth || 720
  const height = container.clientHeight || 560
  d3.select(container).selectAll('*').remove()

  const svg = d3
    .select(container)
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('width', '100%')
    .attr('height', '100%')

  const zoomLayer = svg.append('g')

  // 点击空白处取消选中（关闭详情面板）
  svg.on('click', (event) => {
    if (event.target.tagName === 'svg') {
      emit('select-node', null)
      emit('select-edge', null)
    }
  })

  svg.call(
    d3.zoom().scaleExtent([0.25, 4]).on('zoom', (event) => {
      zoomLayer.attr('transform', event.transform)
    }),
  )

  const links = props.edges.map((edge) => ({ ...edge }))
  const nodes = sizedNodes.value.map((node) => ({ ...node }))

  // 边（可见线条）
  const linkGroup = zoomLayer.append('g')
  const link = linkGroup
    .selectAll('line.visible')
    .data(links)
    .join('line')
    .classed('visible', true)
    .attr('stroke', (d) => (d.id === props.selectedEdgeId ? '#60a5fa' : 'rgba(124, 145, 186, 0.35)'))
    .attr('stroke-width', (d) => (d.id === props.selectedEdgeId ? 2.5 : 1))

  // 边的透明点击区域（更宽，方便点击）
  const linkHit = linkGroup
    .selectAll('line.hitarea')
    .data(links)
    .join('line')
    .classed('hitarea', true)
    .attr('stroke', 'transparent')
    .attr('stroke-width', 12)
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      emit('select-edge', d)
    })

  // 边标签（关系名称）
  const linkLabel = zoomLayer
    .append('g')
    .selectAll('text')
    .data(links)
    .join('text')
    .text((d) => d.name || '')
    .attr('fill', 'rgba(148, 163, 184, 0.6)')
    .attr('font-size', 9)
    .attr('text-anchor', 'middle')
    .attr('pointer-events', 'none')

  // 节点组
  const node = zoomLayer
    .append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .style('cursor', 'pointer')

  // 节点圆形（颜色区分类型）
  const circles = node
    .append('circle')
    .attr('r', (d) => d.visualSize)
    .attr('fill', (d) => getNodeColor(d))
    .attr('stroke', (d) => (d.id === props.selectedNodeId ? '#f8fafc' : '#0f172a'))
    .attr('stroke-width', (d) => (d.id === props.selectedNodeId ? 3 : 1.2))
    .attr('opacity', 0.92)

  // 节点名称标签
  node
    .append('text')
    .text((d) => d.name)
    .attr('dx', (d) => d.visualSize + 6)
    .attr('dy', 4)
    .attr('fill', '#e2e8f0')
    .attr('font-size', 11)
    .attr('pointer-events', 'none')

  simulation = d3
    .forceSimulation(nodes)
    .force('link', d3.forceLink(links).id((d) => d.id).distance(100).strength(0.2))
    .force('charge', d3.forceManyBody().strength(-220))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius((d) => d.visualSize + 12))
    .on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y)

      linkHit
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y)

      linkLabel
        .attr('x', (d) => (d.source.x + d.target.x) / 2)
        .attr('y', (d) => (d.source.y + d.target.y) / 2 - 4)

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

  // 拖拽 + 点击判断（拖拽距离 < 4px 视为点击）
  let dragStartX = 0, dragStartY = 0, dragged = false
  node.call(
    d3
      .drag()
      .on('start', (event, d) => {
        dragStartX = event.x
        dragStartY = event.y
        dragged = false
        if (!event.active) simulation.alphaTarget(0.08).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        const dx = event.x - dragStartX
        const dy = event.y - dragStartY
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4) dragged = true
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        // 保持节点固定在拖拽位置，不会乱飘
        // d.fx = null; d.fy = null  ← 不释放
        if (!dragged) {
          // 没有移动 → 视为点击
          emit('select-node', d.id)
        }
      }),
  )

  // 保存引用，供选中状态更新用
  currentCircles = circles
  currentNodes = nodes
  currentLinks = link
}

// 保存引用，用于更新选中高亮而不重新渲染整个图
let currentCircles = null
let currentNodes = null
let currentLinks = null

function updateSelection() {
  if (currentCircles) {
    currentCircles
      .attr('stroke', (d) => (d.id === props.selectedNodeId ? '#f8fafc' : '#0f172a'))
      .attr('stroke-width', (d) => (d.id === props.selectedNodeId ? 3 : 1.2))
  }
  if (currentLinks) {
    currentLinks
      .attr('stroke', (d) => (d.id === props.selectedEdgeId ? '#60a5fa' : 'rgba(124, 145, 186, 0.35)'))
      .attr('stroke-width', (d) => (d.id === props.selectedEdgeId ? 2.5 : 1))
  }
}

// 数据变化时重新渲染
watch(() => [props.nodes, props.edges, props.scoreMap], render, { deep: true })
// 选中状态变化时只更新高亮，不重新布局
watch(() => [props.selectedNodeId, props.selectedEdgeId], updateSelection)
onMounted(render)
onBeforeUnmount(() => simulation?.stop())

</script>

<template>
  <div ref="containerRef" class="graph-canvas">
    <!-- 图例 -->
    <div class="legend" :class="{ collapsed: legendCollapsed }">
      <div class="legend-header" @click="legendCollapsed = !legendCollapsed">
        <span class="legend-title">实体类型</span>
        <span class="legend-count">{{ entityTypes.length }}</span>
        <span class="legend-toggle">{{ legendCollapsed ? '▸' : '▾' }}</span>
      </div>
      <div v-if="!legendCollapsed" class="legend-body">
        <div v-for="item in legend" :key="item.type" class="legend-item">
          <span class="legend-dot" :style="{ background: item.color }"></span>
          <span class="legend-label">{{ item.type }}</span>
        </div>
      </div>
    </div>
    <!-- 画布 -->
    <div class="canvas-area" />
  </div>
</template>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  min-height: 560px;
  border-radius: 24px;
  background:
    radial-gradient(circle at top, rgba(59, 130, 246, 0.16), transparent 35%),
    linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(8, 15, 29, 0.98));
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  overflow: hidden;
}

.canvas-area {
  width: 100%;
  height: 560px;
  position: relative;
}

/* ---- 图例 ---- */
.legend {
  position: absolute;
  top: 14px;
  left: 14px;
  z-index: 10;
  max-width: 200px;
  max-height: 400px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.18);
  backdrop-filter: blur(12px);
  overflow: hidden;
  transition: all 0.2s;
}

.legend.collapsed {
  max-height: 38px;
}

.legend-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}

.legend-header:hover {
  background: rgba(148, 163, 184, 0.08);
}

.legend-title {
  font-size: 0.78rem;
  font-weight: 600;
  color: #e2e8f0;
}

.legend-count {
  font-size: 0.7rem;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.2);
  color: #93c5fd;
}

.legend-toggle {
  margin-left: auto;
  font-size: 0.72rem;
  color: #64748b;
}

.legend-body {
  padding: 4px 10px 10px;
  overflow-y: auto;
  max-height: 340px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 3px 0;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  opacity: 0.92;
}

.legend-label {
  font-size: 0.76rem;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

</style>
