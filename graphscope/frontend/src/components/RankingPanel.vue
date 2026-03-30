<script setup>
const props = defineProps({
  title: { type: String, default: '节点排行' },
  subtitle: { type: String, default: '' },
  items: { type: Array, default: () => [] },
  selectedNodeId: { type: String, default: null },
  hideTitle: { type: Boolean, default: false },
})

const emit = defineEmits(['select-node'])

function formatScore(score) {
  return Number(score || 0).toLocaleString(undefined, { maximumFractionDigits: 6 })
}
</script>

<template>
  <section class="panel ranking-panel" :class="{ 'no-header': hideTitle }">
    <div v-if="!hideTitle" class="panel-header">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ subtitle }}</p>
      </div>
      <span class="badge">Top {{ items.length }}</span>
    </div>

    <div class="ranking-list" :class="{ 'no-top-margin': hideTitle }">
      <button
        v-for="(item, index) in items"
        :key="`${item.node_id}-${index}`"
        class="ranking-item"
        :class="{ active: item.node_id === selectedNodeId }"
        @click="emit('select-node', item.node_id)"
      >
        <div class="left">
          <span class="index">{{ index + 1 }}</span>
          <div>
            <strong>{{ item.name }}</strong>
            <small>{{ item.labels?.join(' · ') || item.metric }}</small>
          </div>
        </div>
        <span class="score">{{ formatScore(item.score) }}</span>
      </button>
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

.panel.no-header {
  border-radius: 0 0 24px 24px;
  padding-top: 14px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.panel-header h2 {
  margin: 0;
  font-size: 1.05rem;
}

.panel-header p {
  margin: 4px 0 0;
  color: #93a4c3;
}

.badge {
  display: inline-flex;
  align-items: center;
  height: fit-content;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.16);
  color: #bfdbfe;
}

.ranking-list {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.ranking-list.no-top-margin {
  margin-top: 0;
}

.ranking-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px;
  border: 1px solid rgba(148, 163, 184, 0.08);
  border-radius: 16px;
  background: rgba(30, 41, 59, 0.55);
  color: #e2e8f0;
  cursor: pointer;
  transition: 0.2s ease;
}

.ranking-item:hover,
.ranking-item.active {
  border-color: rgba(96, 165, 250, 0.45);
  transform: translateY(-1px);
  background: rgba(37, 99, 235, 0.18);
}

.left {
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
}

.index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.16);
  color: #bfdbfe;
  font-size: 0.85rem;
}

strong {
  display: block;
}

small {
  color: #93a4c3;
}

.score {
  color: #f8fafc;
  font-weight: 700;
}
</style>
