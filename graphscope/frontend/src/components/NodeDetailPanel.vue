<script setup>
import { computed } from 'vue'

const SYSTEM_LABELS = new Set(['Entity', 'Node', 'Episodic'])

// 不在详情中展示的系统属性
const HIDDEN_ATTRS = new Set([
  'uuid', 'name', 'group_id', 'summary', 'created_at', 'embedding',
  'name_embedding', 'labels', 'source_description',
])

const props = defineProps({
  node: { type: Object, default: null },
})

const emit = defineEmits(['close'])

const entityType = computed(() => {
  if (!props.node) return 'Entity'
  for (const lbl of (props.node.labels || [])) {
    if (!SYSTEM_LABELS.has(lbl)) return lbl
  }
  return 'Entity'
})

// 类型 → 标签颜色（与 GraphCanvas 中的 TYPE_COLORS 前几个对应）
const typeColor = computed(() => {
  const colors = {
    Person: '#60a5fa', Organization: '#f472b6', Company: '#34d399',
    University: '#fbbf24', MediaOutlet: '#a78bfa', GovernmentAgency: '#fb923c',
    TechCompany: '#2dd4bf', Researcher: '#f87171', AIModel: '#818cf8',
    Startup: '#4ade80', GameDeveloper: '#e879f9', AIProduct: '#38bdf8',
  }
  return colors[entityType.value] || '#94a3b8'
})

// 基本信息字段
const basicInfo = computed(() => {
  if (!props.node) return []
  const items = []
  if (props.node.name) items.push({ label: 'Name', value: props.node.name })
  if (props.node.id) items.push({ label: 'UUID', value: props.node.id })
  // 从 attributes 中提取 created_at
  const attrs = props.node.attributes || {}
  if (attrs.created_at) {
    const d = new Date(attrs.created_at)
    items.push({ label: 'Created', value: isNaN(d) ? attrs.created_at : d.toLocaleString() })
  }
  return items
})

// 属性字段（排除系统字段）
const properties = computed(() => {
  if (!props.node) return []
  const attrs = props.node.attributes || {}
  return Object.entries(attrs)
    .filter(([k]) => !HIDDEN_ATTRS.has(k))
    .map(([k, v]) => ({
      key: k,
      value: typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? ''),
    }))
    .filter((item) => item.value !== '' && item.value !== 'null')
})

const summary = computed(() => props.node?.summary || '')
</script>

<template>
  <Transition name="slide">
    <div v-if="node" class="node-detail-panel">
      <!-- Header -->
      <div class="detail-header">
        <h3>Node Details</h3>
        <span class="type-badge" :style="{ background: typeColor, color: '#fff' }">
          {{ entityType }}
        </span>
        <button class="close-btn" @click="emit('close')">✕</button>
      </div>

      <!-- Basic Info -->
      <div class="detail-section">
        <div v-for="item in basicInfo" :key="item.label" class="info-row">
          <span class="info-label">{{ item.label }}:</span>
          <span class="info-value">{{ item.value }}</span>
        </div>
      </div>

      <!-- Properties -->
      <div v-if="properties.length" class="detail-section">
        <h4 class="section-title">Properties:</h4>
        <div v-for="prop in properties" :key="prop.key" class="info-row">
          <span class="info-label prop-key">{{ prop.key }}:</span>
          <span class="info-value">{{ prop.value }}</span>
        </div>
      </div>

      <!-- Summary -->
      <div v-if="summary" class="detail-section summary-section">
        <h4 class="section-title">Summary:</h4>
        <p class="summary-text">{{ summary }}</p>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.node-detail-panel {
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

/* Header */
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

/* Sections */
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

/* Info rows */
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
  min-width: 70px;
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

/* Summary */
.summary-section {
  padding-bottom: 16px;
}

.summary-text {
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
.node-detail-panel::-webkit-scrollbar {
  width: 4px;
}

.node-detail-panel::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
}
</style>
