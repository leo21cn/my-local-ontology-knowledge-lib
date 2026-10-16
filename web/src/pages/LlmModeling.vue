<template>
  <div>
    <h3 style="margin-top: 0">LLM 辅助知识建模</h3>
    <el-alert
      v-if="!ontology.classes.length && !ontology.object_properties.length"
      type="warning"
      :closable="false"
      style="margin-bottom: 10px"
      title="本体为空：请先执行下方第一步「本体归纳」并把候选本体在待处理队列中确认，再执行第二步实体抽取。"
    />
    <el-form inline>
      <el-form-item label="范围">
        <el-radio-group v-model="extractForm.scope">
          <el-radio-button value="all">全部文档</el-radio-button>
          <el-radio-button value="file">指定文档</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="extractForm.scope === 'file'" label="文档">
        <el-select v-model="extractForm.file_path" filterable style="width: 360px" placeholder="选择文档">
          <el-option v-for="a in assets" :key="a.rel_path" :label="a.rel_path" :value="a.rel_path" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button @click="$router.push('/pending')">前往待处理队列</el-button>
      </el-form-item>
    </el-form>
    <div style="margin: 8px 0">
      第一步：<el-button size="small" @click="estimateInduct">预估</el-button>
      <el-button size="small" type="primary" :loading="inducting"
                 :disabled="!!(inductTask && inductTask.status === 'running')"
                 @click="confirmInduct">
        {{ inductTask && inductTask.status === 'running' ? '归纳进行中…' : '归纳本体' }}
      </el-button>
      <span v-if="inductEstimate !== null"> 采样切片 {{ inductEstimate.chunks }} 个（上限 20），约 {{ inductEstimate.estimated_minutes }} 分钟</span>
      <span v-if="inductTask" style="margin-left: 10px">
        任务 {{ inductTask.task_id.slice(0, 8) }}：{{ inductTask.status }}，调用 {{ inductTask.extract_calls }}，提案 {{ inductTask.proposals }}，失败 {{ inductTask.extract_failed }}
      </span>
    </div>
    <div style="margin: 8px 0">
      第二步：<el-button size="small" @click="estimateExtract">预估</el-button>
      <el-button size="small" type="warning" :loading="extracting"
                 :disabled="!!(extractTask && extractTask.status === 'running')"
                 @click="confirmExtract">
        {{ extractTask && extractTask.status === 'running' ? '抽取进行中…' : '执行抽取' }}
      </el-button>
      <span v-if="extractEstimate !== null"> 切片 {{ extractEstimate.chunks }} 个，约 {{ extractEstimate.estimated_minutes }} 分钟</span>
      <span v-if="extractTask" style="margin-left: 10px">
        任务 {{ extractTask.task_id.slice(0, 8) }}：{{ extractTask.status }}，调用 {{ extractTask.extract_calls }}，提案 {{ extractTask.proposals }}，丢弃 {{ extractTask.extract_discarded }}，失败 {{ extractTask.extract_failed }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const ontology = ref({ classes: [], object_properties: [], datatype_properties: [] })
const assets = ref([])

const extractForm = reactive({ scope: 'all', file_path: '' })
const extractEstimate = ref(null)
const extractTask = ref(null)
const extracting = ref(false)
const inductEstimate = ref(null)
const inductTask = ref(null)
const inducting = ref(false)
let extractTimer = null
let inductTimer = null

onMounted(async () => {
  await load()
  const tasks = await api.get(`/api/v1/tasks?corpus_id=${id}`)
  const runningInduct = tasks.find((t) => t.kind === 'induct' && t.status === 'running')
  const runningExtract = tasks.find((t) => t.kind === 'extract' && t.status === 'running')
  if (runningInduct) {
    inductTask.value = runningInduct
    pollInduct(runningInduct.task_id)
  }
  if (runningExtract) {
    extractTask.value = runningExtract
    pollExtract(runningExtract.task_id)
  }
})
onUnmounted(() => {
  extractTimer && clearInterval(extractTimer)
  inductTimer && clearInterval(inductTimer)
})

async function load() {
  ontology.value = await api.get(`/api/v1/ontology/${id}`)
  assets.value = await api.get(`/api/v1/corpora/${id}/assets`)
}

function payloadFor() {
  const payload = { scope: extractForm.scope }
  if (extractForm.scope === 'file') {
    if (!extractForm.file_path) {
      ElMessage.error('请选择文档')
      return null
    }
    payload.file_path = extractForm.file_path
  }
  return payload
}

async function estimateInduct() {
  try {
    inductEstimate.value = await api.get(`/api/v1/corpora/${id}/extract/estimate`)
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function pollInduct(taskId) {
  inductTimer && clearInterval(inductTimer)
  inductTimer = setInterval(async () => {
    inductTask.value = await api.get(`/api/v1/tasks/${taskId}`)
    if (['done', 'partial', 'failed'].includes(inductTask.value.status)) {
      clearInterval(inductTimer)
      inductTimer = null
      ElMessage.success('本体归纳完成，请到待处理队列确认候选本体')
    }
  }, 3000)
}

async function confirmInduct() {
  try {
    const payload = payloadFor()
    if (!payload) return
    await ElMessageBox.confirm(
      '本体归纳将采样最多 20 个切片调用 LLM（每个约 1~2 分钟），产出候选类、对象属性与数据属性进入待处理队列，确认后写入本体。确认执行？',
      '本体归纳确认',
      { type: 'warning' }
    )
    inducting.value = true
    const resp = await api.post(`/api/v1/corpora/${id}/induct`, payload)
    inductTask.value = null
    await pollInduct(resp.task_id)
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  } finally {
    inducting.value = false
  }
}

async function estimateExtract() {
  try {
    extractEstimate.value = await api.get(`/api/v1/corpora/${id}/extract/estimate`)
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function pollExtract(taskId) {
  extractTimer && clearInterval(extractTimer)
  extractTimer = setInterval(async () => {
    extractTask.value = await api.get(`/api/v1/tasks/${taskId}`)
    if (['done', 'partial', 'failed'].includes(extractTask.value.status)) {
      clearInterval(extractTimer)
      extractTimer = null
      ElMessage.success('抽取完成，请到待处理队列裁决提案')
    }
  }, 3000)
}

async function confirmExtract() {
  try {
    const payload = payloadFor()
    if (!payload) return
    await ElMessageBox.confirm(
      '抽取将逐切片调用 LLM 模型并按量计费，产出提案进入待处理队列，需人工确认后生效。确认执行？',
      'LLM 抽取确认',
      { type: 'warning' }
    )
    extracting.value = true
    const resp = await api.post(`/api/v1/corpora/${id}/extract`, payload)
    extractTask.value = null
    await pollExtract(resp.task_id)
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  } finally {
    extracting.value = false
  }
}
</script>
