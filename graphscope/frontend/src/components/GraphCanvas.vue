<script setup>
import * as d3 from 'd3'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  scoreMap: { type: Object, default: () => ({}) },
  selectedNodeId: { type: String, default: null },
})

const emit = defineEmits(['select-node'])

const containerRef = ref(null)
let simulation

const sizedNodes = computed(() => {
  const values = Object.values(props.scoreMap)
  const maxScore = values.length ? Math.max(...values) : 1
  return props.nodes.map((node) => ({
    ...node,
    visualSize: 10 + ((props.scoreMap[node.id] || 0) / (maxScore || 1)) * 22,
  }))
})

function render() {
  if (!containerRef.value) return
  const width = containerRef.value.clientWidth || 720
  const height = containerRef.value.clientHeight || 560
  d3.select(containerRef.value).selectAll('*').remove()

  const svg = d3
    .select(containerRef.value)
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('width', '100%')
    .attr('height', '100%')

  const zoomLayer = svg.append('g')
  svg.call(
    d3.zoom().scaleExtent([0.25, 4]).on('zoom', (event) => {
      zoomLayer.attr('transform', event.transform)
    }),
  )

  const color = d3.scaleOrdinal(d3.schemeTableau10)
  const links = props.edges.map((edge) => ({ ...edge }))
  const nodes = sizedNodes.value.map((node) => ({ ...node }))

  const link = zoomLayer
    .append('g')
    .attr('stroke', 'rgba(124, 145, 186, 0.45)')
    .attr('stroke-width', 1.2)
    .selectAll('line')
    .data(links)
    .join('line')

  const node = zoomLayer
    .append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .style('cursor', 'pointer')
    .on('click', (_, datum) => emit('select-node', datum.id))

  node
    .append('circle')
    .attr('r', (d) => d.visualSize)
    .attr('fill', (d) => color((d.labels && d.labels[0]) || 'Entity'))
    .attr('stroke', (d) => (d.id === props.selectedNodeId ? '#f8fafc' : '#182033'))
    .attr('stroke-width', (d) => (d.id === props.selectedNodeId ? 4 : 1.5))
    .attr('opacity', 0.92)

  node
    .append('text')
    .text((d) => d.name)
    .attr('dx', (d) => d.visualSize + 6)
    .attr('dy', 4)
    .attr('fill', '#e2e8f0')
    .attr('font-size', 12)

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

      node.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })

  node.call(
    d3
      .drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.25).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (_, d) => {
        d.fx = _.x
        d.fy = _.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      }),
  )
}

watch(() => [props.nodes, props.edges, props.selectedNodeId, props.scoreMap], render, { deep: true })
onMounted(render)
onBeforeUnmount(() => simulation?.stop())
</script>

<template>
  <div ref="containerRef" class="graph-canvas" />
</template>

<style scoped>
.graph-canvas {
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
</style>
