<script setup>
import { computed } from 'vue'

const HIDDEN_ATTRS = new Set([
  'id', 'source', 'target', 'name', 'fact', 'group_id',
  'weight', 'index', 'vx', 'vy', 'x', 'y', 'fx', 'fy',
])

const props = defineProps({
  edge: { type: Object, default: null },
  nodes: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

const sourceName = computed(() => {
  if (!props.edge) return ''
  const sourceId = props.edge.source?.id || props.edge.source
  const node = props.nodes.find((n) => n.id === sourceId)
  return node?.name || sourceId
})

const targetName = computed(() => {
  if (!props.edge) return ''
  const targetId = props.edge.target?.id || props.edge.target
  const node = props.nodes.find((n) => n.id === targetId)
  return node?.name || targetId
})

const properties = computed(() => {
  if (!props.edge) return []
  const attrs = props.edge.attributes || {}
  return Object.entries(attrs)
    .filter(([k]) => !HIDDEN_ATTRS.has(k))
    .map(([k, v]) => ({
      key: k,
      value: typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? ''),
    }))
    .filter((item) => item.value !== '' && item.value !== 'null')
})
</script>

<template>
  <Transition name="slide">
    <div v-if="edge" class="edge-detail-panel">
      <!-- Header -->
      <div class="detail-header">
        <h3>Edge Details</h3>
        <span class="type-badge">关系</span>
        <button class="close-btn" @click="emit('close')">✕</button>
      </div>

      <!-- 关系名称 -->
      <div class="detail-section">
        <div class="info-row">
          <span class="info-label">关系:</span>
          <span class="info-value relation-name">{{ edge.name || '未命名' }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">源节点:</span>
          <span class="info-value">{{ sourceName }}</span>
        </div>
        <div class="relation-arrow">→</div>
        <div class="info-row">
          <span class="info-label">目标:</span>
          <span class="info-value">{{ targetName }}</span>
        </div>
        <div v-if="edge.weight && edge.weight !== 1" class="info-row">
          <span class="info-label">权重:</span>
          <span class="info-value">{{ edge.weight }}</span>
        </div>
      </div>

      <!-- Fact -->
      <div v-if="edge.fact" class="detail-section">
        <h4 class="section-title">Fact:</h4>
        <p class="fact-text">{{ edge.fact }}</p>
      </div>

      <!-- Properties -->
      <div v-if="properties.length" class="detail-section">
        <h4 class="section-title">Properties:</h4>
        <div v-for="prop in properties" :key="prop.key" class="info-row">
          <span class="info-label prop-key">{{ prop.key }}:</span>
          <span class="info-value">{{ prop.value }}</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.edge-detail-panel {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 15;
  width: 320px;
  max-height: calc(100% - 28px);
  overflow-y: auto;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  color: #1e293b;
  font-size: 0.88rem;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.detail-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
}

.type-badge {
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  white-space: nowrap;
  background: #7c91ba;
  color: #fff;
}

.close-btn {
  margin-left: auto;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.05);
  color: #64748b;
  font-size: 0.82rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.close-btn:hover {
  background: rgba(0, 0, 0, 0.1);
  color: #1e293b;
}

.detail-section {
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.detail-section:last-child {
  border-bottom: none;
}

.section-title {
  margin: 0 0 8px;
  font-size: 0.84rem;
  font-weight: 700;
  color: #334155;
}

.info-row {
  display: flex;
  gap: 10px;
  padding: 4px 0;
  line-height: 1.5;
}

.info-label {
  flex-shrink: 0;
  color: #64748b;
  font-size: 0.82rem;
  min-width: 60px;
}

.prop-key {
  font-family: 'SF Mono', Menlo, monospace;
  color: #9333ea;
  font-size: 0.8rem;
}

.info-value {
  color: #1e293b;
  word-break: break-word;
  font-size: 0.84rem;
}

.relation-name {
  font-weight: 600;
  color: #2563eb;
}

.relation-arrow {
  text-align: center;
  color: #94a3b8;
  font-size: 1.1rem;
  padding: 2px 0;
}

.fact-text {
  margin: 0;
  color: #334155;
  font-size: 0.84rem;
  line-height: 1.7;
}

/* Transition */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.25s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateX(20px);
}

/* Scrollbar */
.edge-detail-panel::-webkit-scrollbar {
  width: 4px;
}

.edge-detail-panel::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}
</style>
