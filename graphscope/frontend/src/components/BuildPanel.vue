<script setup>
import { ref, computed } from 'vue'
import { uploadFiles, generateOntology, buildGraph, fetchBuildTask, fetchProjectOntology, fetchGroups } from '../api'

const props = defineProps({
  groups: { type: Array, default: () => [] },
})
const emit = defineEmits(['build-complete'])

// ============== 模式切换 ==============
const mode = ref('new') // new | incremental

// 步骤: upload → build → done（本体生成在上传后自动进行）
const step = ref('upload') // upload | generating | loading-ontology | build | done
const loading = ref(false)
const error = ref('')

// 上传
const fileInput = ref(null)
const selectedFiles = ref([])
const uploadResult = ref(null)

// 本体
const ontology = ref(null)

// 构建
const graphName = ref('')
const chunkSize = ref(500)
const taskId = ref('')
const taskStatus = ref(null)
const pollTimer = ref(null)

// 增量更新
const selectedGroupId = ref('')

const totalChars = computed(() => uploadResult.value?.total_chars || 0)
const isIncremental = computed(() => mode.value === 'incremental')

const selectedGroupInfo = computed(() => {
  if (!selectedGroupId.value) return null
  return props.groups.find((g) => g.group_id === selectedGroupId.value) || null
})

function switchMode(newMode) {
  if (mode.value === newMode) return
  mode.value = newMode
  reset()
}

function onFileSelect(event) {
  selectedFiles.value = Array.from(event.target.files || [])
}

async function handleUpload() {
  if (!selectedFiles.value.length) return
  loading.value = true
  error.value = ''
  try {
    // 第一步：上传并解析文件
    uploadResult.value = await uploadFiles(selectedFiles.value)

    if (isIncremental.value) {
      // 增量模式：加载已有本体
      step.value = 'loading-ontology'
      await loadExistingOntology()
    } else {
      // 新建模式：LLM 生成本体
      step.value = 'generating'
      await doGenerateOntology()
    }
  } catch (err) {
    error.value = err.message || '上传失败'
    loading.value = false
  }
}

async function loadExistingOntology() {
  try {
    ontology.value = await fetchProjectOntology(selectedGroupId.value)
    step.value = 'build'
  } catch (err) {
    // 项目没有保存本体（旧版创建），回退到 LLM 生成
    error.value = ''
    step.value = 'generating'
    await doGenerateOntology()
  } finally {
    loading.value = false
  }
}

async function doGenerateOntology() {
  try {
    ontology.value = await generateOntology({
      texts: uploadResult.value.texts,
      requirement: '请根据文档内容自动分析，设计合适的实体类型和关系类型',
    })
    step.value = 'build'
  } catch (err) {
    error.value = err.message || '本体生成失败'
  } finally {
    loading.value = false
  }
}

async function handleRegenOntology() {
  loading.value = true
  error.value = ''
  step.value = 'generating'
  await doGenerateOntology()
}

async function handleBuild() {
  if (!isIncremental.value && !graphName.value.trim()) {
    error.value = '请输入项目名称'
    return
  }
  if (isIncremental.value && !selectedGroupId.value) {
    error.value = '请选择目标项目'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const combinedText = uploadResult.value.texts.join('\n\n---\n\n')
    const payload = {
      text: combinedText,
      ontology: {
        entity_types: ontology.value.entity_types,
        edge_types: ontology.value.edge_types,
      },
      graph_name: isIncremental.value
        ? (selectedGroupInfo.value?.project_name || selectedGroupId.value)
        : graphName.value,
      chunk_size: chunkSize.value,
    }
    if (isIncremental.value) {
      payload.group_id = selectedGroupId.value
    }
    const result = await buildGraph(payload)
    taskId.value = result.task_id
    taskStatus.value = result
    startPolling()
  } catch (err) {
    error.value = err.message || '构建启动失败'
    loading.value = false
  }
}

function startPolling() {
  pollTimer.value = setInterval(async () => {
    try {
      const status = await fetchBuildTask(taskId.value)
      taskStatus.value = status
      if (status.status === 'completed' || status.status === 'failed') {
        clearInterval(pollTimer.value)
        loading.value = false
        if (status.status === 'completed') {
          step.value = 'done'
          emit('build-complete', status.result)
        } else {
          error.value = status.error || '构建失败'
        }
      }
    } catch (err) {
      clearInterval(pollTimer.value)
      loading.value = false
      error.value = err.message || '查询任务状态失败'
    }
  }, 2000)
}

function formatGroupLabel(g) {
  const stats = `${g.node_count}节点 ${g.edge_count}边`
  if (g.project_name) return `${g.project_name} — ${stats}`
  const entities = g.top_entities?.length ? g.top_entities.join(', ') : g.group_id.slice(0, 12)
  return `${entities} — ${stats}`
}

function reset() {
  step.value = 'upload'
  selectedFiles.value = []
  uploadResult.value = null
  ontology.value = null
  taskId.value = ''
  taskStatus.value = null
  error.value = ''
  graphName.value = ''
  selectedGroupId.value = ''
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<template>
  <div class="build-panel">
    <div class="build-header">
      <h2>📦 图谱构建</h2>
      <p class="build-desc">上传文档 → 生成本体 → 构建知识图谱，写入 Neo4j</p>
    </div>

    <!-- 模式切换 -->
    <div class="mode-switcher">
      <button :class="{ active: mode === 'new' }" @click="switchMode('new')">🆕 新建图谱</button>
      <button :class="{ active: mode === 'incremental' }" @click="switchMode('incremental')">📥 增量更新</button>
    </div>

    <!-- 步骤指示器 -->
    <div class="step-bar">
      <span :class="{ active: step === 'upload' || step === 'generating' || step === 'loading-ontology', done: step === 'build' || step === 'done' }">
        ① {{ isIncremental ? '选择项目 & 上传' : '上传 & 分析' }}
      </span>
      <span class="step-arrow">→</span>
      <span :class="{ active: step === 'build', done: step === 'done' }">② 确认 & 构建</span>
      <span class="step-arrow">→</span>
      <span :class="{ active: step === 'done' }">③ 完成</span>
    </div>

    <div v-if="error" class="build-error">{{ error }}</div>

    <!-- Step 1: 上传文件 -->
    <div v-if="step === 'upload'" class="step-content">
      <!-- 新建模式：项目名称 -->
      <label v-if="!isIncremental">
        <span>项目名称</span>
        <input v-model="graphName" type="text" placeholder="例如：三国演义人物关系图谱" />
      </label>

      <!-- 增量模式：选择已有项目 -->
      <div v-if="isIncremental" class="incremental-selector">
        <label>
          <span>选择目标项目</span>
          <select v-model="selectedGroupId">
            <option value="">请选择要更新的项目…</option>
            <option v-for="g in groups" :key="g.group_id" :value="g.group_id">
              {{ formatGroupLabel(g) }}
            </option>
          </select>
        </label>
        <div v-if="selectedGroupInfo" class="selected-project-info">
          <span>📊 当前：{{ selectedGroupInfo.node_count }} 节点 · {{ selectedGroupInfo.edge_count }} 边</span>
          <span v-if="selectedGroupInfo.label_sample?.length" class="project-labels">
            {{ selectedGroupInfo.label_sample.slice(0, 3).join(', ') }}
          </span>
        </div>
      </div>

      <label class="file-label">
        <span>选择{{ isIncremental ? '新增' : '' }}文件（支持 PDF、Markdown、TXT）</span>
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".pdf,.md,.markdown,.txt"
          @change="onFileSelect"
        />
      </label>
      <div v-if="selectedFiles.length" class="file-list">
        <div v-for="(f, i) in selectedFiles" :key="i" class="file-item">
          📄 {{ f.name }} <span class="file-size">({{ (f.size / 1024).toFixed(1) }} KB)</span>
        </div>
      </div>
      <button
        class="primary"
        :disabled="!selectedFiles.length || (!isIncremental && !graphName.trim()) || (isIncremental && !selectedGroupId) || loading"
        @click="handleUpload"
      >
        {{ loading ? '上传解析中…' : isIncremental ? '上传并准备更新' : '上传并解析' }}
      </button>
    </div>

    <!-- 中间状态: 正在自动生成本体 -->
    <div v-if="step === 'generating'" class="step-content">
      <div class="upload-summary">
        ✅ 已解析 {{ uploadResult?.files?.length }} 个文件，共 {{ totalChars.toLocaleString() }} 字
      </div>
      <div class="generating-state">
        <div class="generating-spinner"></div>
        <p>🔍 LLM 正在自动分析文档内容，生成知识图谱本体…</p>
        <p class="generating-hint">根据文档内容自动识别实体类型和关系类型，无需手动输入</p>
      </div>
    </div>

    <!-- 中间状态: 正在加载已有本体 -->
    <div v-if="step === 'loading-ontology'" class="step-content">
      <div class="upload-summary">
        ✅ 已解析 {{ uploadResult?.files?.length }} 个文件，共 {{ totalChars.toLocaleString() }} 字
      </div>
      <div class="generating-state">
        <div class="generating-spinner"></div>
        <p>📂 正在加载项目已有的本体定义…</p>
        <p class="generating-hint">增量更新将复用原始项目的实体和关系类型</p>
      </div>
    </div>

    <!-- Step 2: 确认本体 & 构建 -->
    <div v-if="step === 'build'" class="step-content">
      <!-- 增量更新提示 -->
      <div v-if="isIncremental" class="incremental-notice">
        📥 增量更新模式 → 新数据将追加到项目 <strong>{{ selectedGroupInfo?.project_name || selectedGroupId }}</strong>
      </div>

      <div class="ontology-preview">
        <div class="ontology-header">
          <h3>{{ isIncremental ? '项目本体（已有）' : '本体预览' }}</h3>
          <button class="regen-btn" :disabled="loading" @click="handleRegenOntology">🔄 {{ isIncremental ? '用新文档重新生成' : '重新生成' }}</button>
        </div>
        <p class="ontology-summary">{{ ontology?.analysis_summary }}</p>
        <div class="ontology-grid">
          <div>
            <h4>实体类型 ({{ ontology?.entity_types?.length || 0 }})</h4>
            <div v-for="et in ontology?.entity_types" :key="et.name" class="type-chip entity-chip">
              <strong>{{ et.name }}</strong>
              <span>{{ et.description }}</span>
            </div>
          </div>
          <div>
            <h4>关系类型 ({{ ontology?.edge_types?.length || 0 }})</h4>
            <div v-for="et in ontology?.edge_types" :key="et.name" class="type-chip edge-chip">
              <strong>{{ et.name }}</strong>
              <span>{{ et.description }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="build-options">
        <label>
          <span>分块大小（字符）</span>
          <input v-model.number="chunkSize" type="number" min="100" max="2000" />
        </label>
      </div>

      <!-- 构建进度 -->
      <div v-if="taskStatus" class="progress-bar-wrapper">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: (taskStatus.progress || 0) + '%' }"></div>
        </div>
        <span class="progress-text">{{ taskStatus.progress || 0 }}% — {{ taskStatus.message }}</span>
      </div>

      <button class="primary" :disabled="loading" @click="handleBuild">
        {{ loading ? (isIncremental ? '更新中…' : '构建中…') : (isIncremental ? '开始增量更新' : '开始构建图谱') }}
      </button>
    </div>

    <!-- Step 3: 完成 -->
    <div v-if="step === 'done'" class="step-content">
      <div class="done-summary">
        <p class="done-icon">🎉</p>
        <h3>{{ taskStatus?.result?.is_incremental ? '增量更新完成！' : '图谱构建完成！' }}</h3>
        <div class="done-stats">
          <div><strong>Group ID:</strong> {{ taskStatus?.result?.group_id }}</div>
          <div><strong>节点数:</strong> {{ taskStatus?.result?.node_count }}</div>
          <div><strong>边数:</strong> {{ taskStatus?.result?.edge_count }}</div>
          <div><strong>文本块:</strong> {{ taskStatus?.result?.chunks_total }} (失败: {{ taskStatus?.result?.chunks_failed }})</div>
        </div>
        <p class="done-hint">
          {{ taskStatus?.result?.is_incremental ? '新数据已追加到图谱，切换到分析页查看更新后的图谱。' : '刷新页面后可在项目列表中选择新图谱进行分析' }}
        </p>
      </div>
      <button class="primary" @click="reset">{{ isIncremental ? '继续更新' : '构建新图谱' }}</button>
    </div>
  </div>
</template>

<style scoped>
.build-panel {
  padding: 22px 24px;
  border-radius: 24px;
  background: rgba(15, 23, 42, 0.76);
  border: 1px solid rgba(148, 163, 184, 0.14);
  backdrop-filter: blur(18px);
}

.build-header h2 {
  margin: 0;
  font-size: 1.15rem;
}

.build-desc {
  margin: 6px 0 0;
  color: #94a3b8;
  font-size: 0.85rem;
}

/* 模式切换 */
.mode-switcher {
  display: flex;
  gap: 6px;
  margin: 16px 0 4px;
}

.mode-switcher button {
  width: auto;
  margin: 0;
  padding: 8px 18px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.5);
  color: #94a3b8;
  font: inherit;
  font-size: 0.86rem;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-switcher button.active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.25), rgba(124, 58, 237, 0.25));
  border-color: rgba(59, 130, 246, 0.35);
  color: #f1f5f9;
  font-weight: 600;
}

.mode-switcher button:hover:not(.active) {
  background: rgba(15, 23, 42, 0.8);
  color: #cbd5e1;
}

/* 增量选择器 */
.incremental-selector {
  display: grid;
  gap: 8px;
}

.incremental-selector select {
  width: 100%;
  margin-top: 6px;
  padding: 10px 14px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.86);
  color: #f8fafc;
  font: inherit;
}

.selected-project-info {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
  font-size: 0.84rem;
  color: #93c5fd;
}

.project-labels {
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.1);
  color: #94a3b8;
  font-size: 0.78rem;
}

/* 增量提示条 */
.incremental-notice {
  padding: 10px 16px;
  border-radius: 12px;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  color: #fbbf24;
  font-size: 0.88rem;
}

.incremental-notice strong {
  color: #fde68a;
}

.step-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0;
  font-size: 0.84rem;
  color: #64748b;
}

.step-bar span.active {
  color: #93c5fd;
  font-weight: 600;
}

.step-bar span.done {
  color: #86efac;
}

.step-arrow {
  color: #475569;
}

.build-error {
  margin: 12px 0;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(127, 29, 29, 0.35);
  border: 1px solid rgba(248, 113, 113, 0.35);
  color: #fecaca;
  font-size: 0.88rem;
}

.step-content {
  display: grid;
  gap: 16px;
}

.file-label span {
  display: block;
  color: #93a4c3;
  font-size: 0.85rem;
  margin-bottom: 6px;
}

.file-label input[type="file"] {
  width: 100%;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.86);
  color: #f8fafc;
}

.file-list {
  display: grid;
  gap: 6px;
}

.file-item {
  font-size: 0.88rem;
  color: #cbd5e1;
}

.file-size {
  color: #64748b;
}

.upload-summary {
  padding: 12px 16px;
  border-radius: 14px;
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: #86efac;
  font-size: 0.9rem;
}

.generating-state {
  text-align: center;
  padding: 24px 16px;
}

.generating-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(148, 163, 184, 0.15);
  border-top-color: #93c5fd;
  border-radius: 50%;
  margin: 0 auto 14px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.generating-state p {
  margin: 6px 0;
  color: #cbd5e1;
  font-size: 0.92rem;
}

.generating-hint {
  color: #64748b !important;
  font-size: 0.82rem !important;
}

.ontology-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.ontology-header h3 {
  margin: 0;
  font-size: 1rem;
}

.regen-btn {
  padding: 5px 12px;
  border-radius: 10px;
  background: rgba(148, 163, 184, 0.1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  color: #93a4c3;
  font-size: 0.78rem;
  cursor: pointer;
  transition: all 0.2s;
}

.regen-btn:hover {
  background: rgba(148, 163, 184, 0.18);
  color: #e2e8f0;
}

.ontology-preview {
  border-radius: 16px;
  padding: 16px;
  background: rgba(15, 23, 42, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.ontology-summary {
  color: #94a3b8;
  font-size: 0.88rem;
  margin: 0 0 14px;
  line-height: 1.6;
}

.ontology-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.ontology-grid h4 {
  margin: 0 0 10px;
  font-size: 0.88rem;
  color: #93c5fd;
}

.type-chip {
  margin-bottom: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 0.82rem;
  line-height: 1.5;
}

.entity-chip {
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
}

.edge-chip {
  background: rgba(168, 85, 247, 0.08);
  border: 1px solid rgba(168, 85, 247, 0.15);
}

.type-chip strong {
  display: block;
  color: #e2e8f0;
}

.type-chip span {
  color: #94a3b8;
  font-size: 0.78rem;
}

.build-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.progress-bar-wrapper {
  display: grid;
  gap: 6px;
}

.progress-bar {
  height: 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.12);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2563eb, #7c3aed);
  transition: width 0.5s ease;
}

.progress-text {
  font-size: 0.82rem;
  color: #93a4c3;
}

.done-summary {
  text-align: center;
  padding: 20px;
}

.done-icon {
  font-size: 2.5rem;
  margin: 0;
}

.done-summary h3 {
  margin: 10px 0 16px;
}

.done-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  text-align: left;
  padding: 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.5);
  font-size: 0.88rem;
  color: #cbd5e1;
}

.done-hint {
  margin-top: 14px;
  color: #64748b;
  font-size: 0.84rem;
}

label span {
  display: block;
  color: #93a4c3;
  font-size: 0.85rem;
}

input,
textarea {
  width: 100%;
  margin-top: 6px;
  padding: 10px 14px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.86);
  color: #f8fafc;
  font: inherit;
}

textarea {
  resize: vertical;
}

button.primary {
  padding: 12px 14px;
  border-radius: 16px;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  border: none;
  color: #f8fafc;
  font: inherit;
  cursor: pointer;
  box-shadow: 0 16px 32px rgba(59, 130, 246, 0.2);
}

button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
</style>
