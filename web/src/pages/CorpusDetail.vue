<template>
  <div v-if="corpus">
    <el-descriptions :column="2" border>
      <el-descriptions-item label="名称">{{ corpus.name }}</el-descriptions-item>
      <el-descriptions-item label="子目录">{{ corpus.subdir }}</el-descriptions-item>
      <el-descriptions-item label="嵌入模型">{{ corpus.embedding_model }}</el-descriptions-item>
      <el-descriptions-item label="向量维度">{{ corpus.vector_dim }}</el-descriptions-item>
      <el-descriptions-item label="切片上限">{{ corpus.chunk_max_chars }}</el-descriptions-item>
      <el-descriptions-item label="重叠字符">{{ corpus.chunk_overlap }}</el-descriptions-item>
      <el-descriptions-item label="图谱扩展">{{ corpus.graph_expand_enabled ? '开' : '关' }}</el-descriptions-item>
      <el-descriptions-item label="图谱权重">{{ corpus.graph_weight }}</el-descriptions-item>
      <el-descriptions-item label="点数">{{ corpus.points }}</el-descriptions-item>
      <el-descriptions-item label="归档">{{ corpus.archived ? '是' : '否' }}</el-descriptions-item>
    </el-descriptions>
    <div style="margin: 12px 0">
      <el-button :type="corpus.archived ? 'success' : 'warning'" @click="toggleArchive">
        {{ corpus.archived ? '取消归档' : '归档' }}
      </el-button>
      <span style="color: #909399; font-size: 12px; margin-left: 8px">
        {{ corpus.archived ? '归档后不再轮询同步，检索跳过该库' : '归档可停止轮询同步并让检索跳过该库，可随时取消' }}
      </span>
    </div>
    <el-alert type="info" :closable="false" style="margin: 12px 0"
      title="嵌入模型与维度不可修改；如需更换请新建库指向同一子目录，同步验证通过后归档旧库。" />

    <el-card header="同步" style="margin-bottom: 12px">
      <el-button type="primary" :loading="syncing"
                 :disabled="!!(task && task.status === 'running')" @click="triggerSync">
        {{ task && task.status === 'running' ? '任务进行中…' : '触发同步' }}
      </el-button>
      <el-button @click="$router.push(`/corpora/${id}/chunks`)">切片查看</el-button>
      <div v-if="task" style="margin-top: 8px">
        任务 {{ task.task_id }}：状态 {{ task.status }}，
        文档 {{ task.doc_total }} / 变更 {{ task.doc_changed }} / 移除 {{ task.doc_removed }}，
        切片 {{ task.chunks }}，令牌 {{ task.tokens }}，重试 {{ task.embed_retries }}，
        费用估算 {{ task.cost_estimate }}<span v-if="task.error_code">，错误码 {{ task.error_code }}</span>
      </div>
    </el-card>

    <el-card header="索引重建">
      <el-button :loading="rebuilding === 'structure'"
                 :disabled="!!(task && task.status === 'running')"
                 @click="rebuild('structure')">结构重建（不产生嵌入费用）</el-button>
      <el-button type="warning" :loading="rebuilding === 'reembed'"
                 :disabled="!!(task && task.status === 'running')"
                 @click="confirmReembed">全量重嵌入</el-button>
      <div v-if="estimate" style="margin-top: 8px">
        预估：切片 {{ estimate.chunks }}，嵌入请求 {{ estimate.embed_requests }} 条，费用估算 {{ estimate.cost_estimate }}
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const corpus = ref(null)
const task = ref(null)
const estimate = ref(null)
const syncing = ref(false)
const rebuilding = ref('')
let timer = null

onMounted(load)
onUnmounted(() => timer && clearInterval(timer))

async function load() {
  corpus.value = await api.get(`/api/v1/corpora/${id}`)
}

async function toggleArchive() {
  try {
    await api.patch(`/api/v1/corpora/${id}`, { archived: !corpus.value.archived })
    ElMessage.success(corpus.value.archived ? '已取消归档' : '已归档')
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function poll(taskId) {
  timer && clearInterval(timer)
  timer = setInterval(async () => {
    task.value = await api.get(`/api/v1/tasks/${taskId}`)
    if (['done', 'partial', 'failed'].includes(task.value.status)) {
      clearInterval(timer)
      timer = null
      await load()
    }
  }, 2000)
}

async function triggerSync() {
  syncing.value = true
  try {
    const resp = await api.post(`/api/v1/corpora/${id}/sync`, { scope: 'all' })
    await poll(resp.task_id)
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    syncing.value = false
  }
}

async function rebuild(mode) {
  rebuilding.value = mode
  try {
    const resp = await api.post(`/api/v1/corpora/${id}/rebuild`, { mode })
    await poll(resp.task_id)
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    rebuilding.value = ''
  }
}

async function confirmReembed() {
  try {
    estimate.value = await api.get(`/api/v1/corpora/${id}/rebuild/estimate`)
    await ElMessageBox.confirm(
      `将删除现有索引并重新嵌入：切片 ${estimate.value.chunks} 个，嵌入请求 ${estimate.value.embed_requests} 条，费用估算 ${estimate.value.cost_estimate}。确认执行？`,
      '全量重嵌入二次确认',
      { type: 'warning' }
    )
    await rebuild('reembed')
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  }
}
</script>
