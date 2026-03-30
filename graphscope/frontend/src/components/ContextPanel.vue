<script setup>
const props = defineProps({
  context: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})
</script>

<template>
  <section class="panel context-panel">
    <div class="panel-header">
      <h2>GraphRAG 上下文</h2>
      <p>面向 Agent / 报告生成的结构化上下文输出</p>
    </div>

    <div v-if="loading" class="placeholder">正在生成结构感知上下文…</div>
    <div v-else-if="context" class="context-body">
      <pre>{{ context.summary }}</pre>
      <div class="citation-list" v-if="context.citations?.length">
        <strong>引用线索</strong>
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
}

pre {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
  font-family: inherit;
  color: #dbeafe;
}

.citation-list {
  margin-top: 18px;
}

ul {
  margin: 10px 0 0;
  padding-left: 18px;
}
</style>
