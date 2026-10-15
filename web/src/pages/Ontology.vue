<template>
  <div>
    <el-button type="primary" style="margin-bottom: 12px" @click="showClass = true">新建类</el-button>
    <el-button style="margin-bottom: 12px" @click="showObjProp = true">新建对象属性</el-button>
    <el-button style="margin-bottom: 12px" @click="showDataProp = true">新建数据属性</el-button>
    <el-button style="margin-bottom: 12px" @click="exportTtl">导出 TTL</el-button>

    <el-card header="类">
      <el-table :data="ontology.classes" border>
        <el-table-column prop="label_zh" label="名称" />
        <el-table-column prop="iri" label="IRI" show-overflow-tooltip />
        <el-table-column label="父类">
          <template #default="{ row }">
            <el-tag v-for="p in row.parent_iris" :key="p" size="small" style="margin-right: 4px">{{ p.split('#').pop() }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="editClass(row)">修改</el-button>
            <el-button size="small" type="danger" @click="removeClass(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card header="对象属性" style="margin-top: 12px">
      <el-table :data="ontology.object_properties" border>
        <el-table-column prop="label_zh" label="名称" />
        <el-table-column prop="iri" label="IRI" show-overflow-tooltip />
        <el-table-column label="domain" prop="domain_iri" show-overflow-tooltip />
        <el-table-column label="range" prop="range_iri" show-overflow-tooltip />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="editObjProp(row)">修改</el-button>
            <el-button size="small" type="danger" @click="removeObjProp(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card header="数据属性" style="margin-top: 12px">
      <el-table :data="ontology.datatype_properties" border>
        <el-table-column prop="label_zh" label="名称" />
        <el-table-column prop="iri" label="IRI" show-overflow-tooltip />
        <el-table-column prop="xsd_range" label="XSD 类型" show-overflow-tooltip />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="editDataProp(row)">修改</el-button>
            <el-button size="small" type="danger" @click="removeDataProp(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card header="LLM 辅助抽取" style="margin-top: 12px">
      <el-form inline>
        <el-form-item label="范围">
          <el-radio-group v-model="extractForm.scope">
            <el-radio-button value="all">全部文档</el-radio-button>
            <el-radio-button value="file">指定文档</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="extractForm.scope === 'file'" label="文档">
          <el-select v-model="extractForm.file_path" filterable style="width: 300px" placeholder="选择文档">
            <el-option v-for="a in assets" :key="a.rel_path" :label="a.rel_path" :value="a.rel_path" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="estimateExtract">预估</el-button>
        </el-form-item>
        <el-form-item>
          <el-button type="warning" :loading="extracting" @click="confirmExtract">执行抽取</el-button>
        </el-form-item>
        <el-form-item>
          <el-button @click="$router.push('/pending')">前往待处理队列</el-button>
        </el-form-item>
      </el-form>
      <div v-if="extractEstimate !== null" style="margin-top: 6px">
        预估：切片 {{ extractEstimate.chunks }} 个（即抽取调用数上限）
      </div>
      <div v-if="extractTask" style="margin-top: 6px">
        任务 {{ extractTask.task_id }}：状态 {{ extractTask.status }}，
        调用 {{ extractTask.extract_calls }}，令牌 {{ extractTask.extract_tokens }}，
        提案 {{ extractTask.proposals }}，丢弃 {{ extractTask.extract_discarded }}，
        失败 {{ extractTask.extract_failed }}，
        费用估算 {{ extractTask.extract_cost_estimate }}
      </div>
    </el-card>

    <el-dialog v-model="showClass" :title="classForm.iri && editing ? '修改类' : '新建类'" width="560px">
      <el-form :model="classForm" label-width="120px">
        <el-form-item label="IRI"><el-input v-model="classForm.iri" :disabled="editing" /></el-form-item>
        <el-form-item label="本地名"><el-input v-model="classForm.prefix_local" /></el-form-item>
        <el-form-item label="中文标签"><el-input v-model="classForm.label_zh" /></el-form-item>
        <el-form-item label="定义"><el-input v-model="classForm.definition" /></el-form-item>
        <el-form-item label="父类 IRI"><el-input v-model="parentText" placeholder="逗号分隔" /></el-form-item>
        <el-form-item label="别名"><el-input v-model="aliasText" placeholder="逗号分隔" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showClass = false">取消</el-button>
        <el-button type="primary" @click="saveClass">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showObjProp" :title="editing ? '修改对象属性' : '新建对象属性'" width="560px">
      <el-form :model="objPropForm" label-width="120px">
        <el-form-item label="IRI"><el-input v-model="objPropForm.iri" :disabled="editing" /></el-form-item>
        <el-form-item label="本地名"><el-input v-model="objPropForm.prefix_local" /></el-form-item>
        <el-form-item label="中文标签"><el-input v-model="objPropForm.label_zh" /></el-form-item>
        <el-form-item label="定义"><el-input v-model="objPropForm.definition" /></el-form-item>
        <el-form-item label="domain IRI"><el-input v-model="objPropForm.domain_iri" /></el-form-item>
        <el-form-item label="range IRI"><el-input v-model="objPropForm.range_iri" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showObjProp = false">取消</el-button>
        <el-button type="primary" @click="saveObjProp">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showDataProp" :title="editing ? '修改数据属性' : '新建数据属性'" width="560px">
      <el-form :model="dataPropForm" label-width="120px">
        <el-form-item label="IRI"><el-input v-model="dataPropForm.iri" :disabled="editing" /></el-form-item>
        <el-form-item label="本地名"><el-input v-model="dataPropForm.prefix_local" /></el-form-item>
        <el-form-item label="中文标签"><el-input v-model="dataPropForm.label_zh" /></el-form-item>
        <el-form-item label="定义"><el-input v-model="dataPropForm.definition" /></el-form-item>
        <el-form-item label="domain IRI"><el-input v-model="dataPropForm.domain_iri" /></el-form-item>
        <el-form-item label="XSD range"><el-input v-model="dataPropForm.xsd_range" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDataProp = false">取消</el-button>
        <el-button type="primary" @click="saveDataProp">保存</el-button>
      </template>
    </el-dialog>
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
const showClass = ref(false)
const showObjProp = ref(false)
const showDataProp = ref(false)
const editing = ref(false)
const parentText = ref('')
const aliasText = ref('')

const classForm = reactive({ iri: '', prefix_local: '', label_zh: '', definition: '' })
const objPropForm = reactive({ iri: '', prefix_local: '', label_zh: '', definition: '', domain_iri: '', range_iri: '' })
const dataPropForm = reactive({ iri: '', prefix_local: '', label_zh: '', definition: '', domain_iri: '', xsd_range: 'http://www.w3.org/2001/XMLSchema#string' })

const extractForm = reactive({ scope: 'all', file_path: '' })
const assets = ref([])
const extractEstimate = ref(null)
const extractTask = ref(null)
const extracting = ref(false)
let extractTimer = null

onMounted(load)
onUnmounted(() => extractTimer && clearInterval(extractTimer))

async function load() {
  ontology.value = await api.get(`/api/v1/ontology/${id}`)
  assets.value = await api.get(`/api/v1/corpora/${id}/assets`)
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
    const payload = { scope: extractForm.scope }
    if (extractForm.scope === 'file') {
      if (!extractForm.file_path) {
        ElMessage.error('请选择文档')
        return
      }
      payload.file_path = extractForm.file_path
    }
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

function listText(value) {
  return (value || []).join(',')
}

function encodeIri(iri) {
  return encodeURIComponent(iri)
}

async function saveClass() {
  try {
    const payload = {
      ...classForm,
      parent_iris: parentText.value ? parentText.value.split(',').map((t) => t.trim()) : [],
      aliases: aliasText.value ? aliasText.value.split(',').map((t) => t.trim()) : []
    }
    if (editing.value) {
      await api.patch(`/api/v1/ontology/classes/${encodeIri(classForm.iri)}?corpus_id=${id}`, payload)
    } else {
      await api.post(`/api/v1/ontology/classes?corpus_id=${id}`, payload)
    }
    showClass.value = false
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function editClass(row) {
  Object.assign(classForm, row)
  parentText.value = listText(row.parent_iris)
  aliasText.value = listText(row.aliases)
  editing.value = true
  showClass.value = true
}

async function removeClass(row) {
  try {
    await ElMessageBox.confirm(`删除类「${row.label_zh}」后，其声明实例将转待处理队列。确认？`, '删除确认', { type: 'warning' })
    const resp = await api.del(`/api/v1/ontology/classes/${encodeIri(row.iri)}?corpus_id=${id}`)
    ElMessage.success(`已删除，受影响实例 ${resp.affected_entities} 个`)
    await load()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  }
}

async function saveObjProp() {
  try {
    const payload = { ...objPropForm }
    if (editing.value) {
      await api.patch(`/api/v1/ontology/object-properties/${encodeIri(objPropForm.iri)}?corpus_id=${id}`, payload)
    } else {
      await api.post(`/api/v1/ontology/object-properties?corpus_id=${id}`, payload)
    }
    showObjProp.value = false
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function editObjProp(row) {
  Object.assign(objPropForm, row)
  editing.value = true
  showObjProp.value = true
}

async function removeObjProp(row) {
  try {
    await ElMessageBox.confirm(`删除属性「${row.label_zh}」后，以它建立的已确认关系将转待处理队列。确认？`, '删除确认', { type: 'warning' })
    const resp = await api.del(`/api/v1/ontology/object-properties/${encodeIri(row.iri)}?corpus_id=${id}`)
    ElMessage.success(`已删除，受影响关系 ${resp.affected_relations} 个`)
    await load()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  }
}

async function saveDataProp() {
  try {
    const payload = { ...dataPropForm }
    if (editing.value) {
      await api.patch(`/api/v1/ontology/datatype-properties/${encodeIri(dataPropForm.iri)}?corpus_id=${id}`, payload)
    } else {
      await api.post(`/api/v1/ontology/datatype-properties?corpus_id=${id}`, payload)
    }
    showDataProp.value = false
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function editDataProp(row) {
  Object.assign(dataPropForm, row)
  editing.value = true
  showDataProp.value = true
}

async function removeDataProp(row) {
  try {
    await ElMessageBox.confirm(`删除数据属性「${row.label_zh}」？`, '删除确认', { type: 'warning' })
    await api.del(`/api/v1/ontology/datatype-properties/${encodeIri(row.iri)}?corpus_id=${id}`)
    await load()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  }
}

async function exportTtl() {
  const resp = await api.raw(`/api/v1/ontology/export/${id}`)
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${id}.ttl`
  link.click()
  URL.revokeObjectURL(url)
}
</script>
