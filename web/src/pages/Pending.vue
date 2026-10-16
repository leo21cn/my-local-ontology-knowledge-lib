<template>
  <div>
    <el-tabs v-model="kind">
      <el-tab-pane label="本体提案" name="ontology_proposal" />
      <el-tab-pane label="实体提案" name="proposal" />
      <el-tab-pane label="关系提案" name="relation_proposal" />
      <el-tab-pane label="校验违规" name="violation" />
      <el-tab-pane label="嵌入失败" name="embed_failed" />
      <el-tab-pane label="抽取失败" name="extract_failed" />
    </el-tabs>

    <el-alert
      v-if="kind === 'ontology_proposal'"
      type="info"
      :closable="false"
      style="margin-bottom: 10px"
      title="建议先确认「类」提案，再确认「对象属性」提案：对象属性的 domain/range 引用类标签，对应类未确认时确认会失败。"
    />

    <el-table :data="grouped" border :row-class-name="rowClass">
      <el-table-column prop="pid" label="ID" width="260" show-overflow-tooltip />
      <el-table-column label="摘要">
        <template #default="{ row }">
          <pre style="white-space: pre-wrap; margin: 0">{{ JSON.stringify(row.payload, null, 2) }}</pre>
        </template>
      </el-table-column>
      <el-table-column prop="attempts" label="尝试次数" width="100" />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="340">
        <template #default="{ row }">
          <el-button v-if="['proposal', 'relation_proposal', 'ontology_proposal'].includes(row.kind)" size="small" type="primary" @click="resolve(row, 'confirm')">确认</el-button>
          <el-button v-if="row.kind === 'ontology_proposal'" size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="resolve(row, 'reject')">拒绝</el-button>
          <el-button v-if="row.kind === 'proposal'" size="small" @click="retypeFor = row; retypeDialog = true">改类型</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="retypeDialog" title="改类型（retype）" width="420px">
      <el-form label-width="100px">
        <el-form-item label="新类 IRI"><el-input v-model="retypeIri" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="retypeDialog = false">取消</el-button>
        <el-button type="primary" @click="doRetype">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editDialog" title="编辑本体提案" width="560px">
      <el-form label-width="120px">
        <el-form-item label="要素类型">
          <el-input :model-value="editForm.element_kind" disabled />
        </el-form-item>
        <el-form-item label="本地名（英文）">
          <el-input v-model="editForm.local_name" />
          <div class="hint">IRI 预览：{{ iriPreview }}</div>
        </el-form-item>
        <el-form-item label="中文标签"><el-input v-model="editForm.label" /></el-form-item>
        <el-form-item label="定义"><el-input v-model="editForm.definition" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="别名">
          <el-input v-model="editForm.aliases_text" placeholder="逗号分隔，可留空" />
        </el-form-item>
        <template v-if="editForm.element_kind === 'object_property'">
          <el-form-item label="domain 类标签">
            <el-select v-model="editForm.domain" filterable allow-create placeholder="选择或输入已确认类的标签">
              <el-option v-for="c in classLabels" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="range 类标签">
            <el-select v-model="editForm.range" filterable allow-create placeholder="选择或输入已确认类的标签">
              <el-option v-for="c in classLabels" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
        </template>
        <template v-if="editForm.element_kind === 'datatype_property'">
          <el-form-item label="domain 类标签">
            <el-select v-model="editForm.domain" filterable allow-create placeholder="选择或输入已确认类的标签">
              <el-option v-for="c in classLabels" :key="c" :label="c" :value="c" />
            </el-select>
          </el-form-item>
          <el-form-item label="range xsd 类型">
            <el-select v-model="editForm.range" placeholder="选择 xsd 类型">
              <el-option v-for="x in XSD_OPTIONS" :key="x.value" :label="x.label" :value="x.value" />
            </el-select>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const items = ref([])
const kind = ref('ontology_proposal')
const highlightPid = ref('')
const retypeDialog = ref(false)
const retypeFor = ref(null)
const retypeIri = ref('')
const editDialog = ref(false)
const editFor = ref(null)
const editForm = ref({})
const classLabels = ref([])
const XSD_OPTIONS = [
  { label: 'string（字符串/文本）', value: 'http://www.w3.org/2001/XMLSchema#string' },
  { label: 'integer（整数）', value: 'http://www.w3.org/2001/XMLSchema#integer' },
  { label: 'date（日期）', value: 'http://www.w3.org/2001/XMLSchema#date' },
  { label: 'dateTime（日期时间）', value: 'http://www.w3.org/2001/XMLSchema#dateTime' },
  { label: 'boolean（布尔）', value: 'http://www.w3.org/2001/XMLSchema#boolean' },
  { label: 'decimal（小数/数值）', value: 'http://www.w3.org/2001/XMLSchema#decimal' }
]

const grouped = computed(() => {
  const list = items.value.filter((i) => i.kind === kind.value)
  if (kind.value === 'ontology_proposal') {
    return [...list].sort((a, b) => {
      const rank = (x) => (x.payload?.element_kind === 'class' ? 0 : 1)
      return rank(a) - rank(b)
    })
  }
  return list
})
const iriPreview = computed(() => {
  const p = editForm.value?.iri_preview || 'http://kb.local/o/#'
  const base = p.slice(0, p.lastIndexOf('#') + 1)
  return base + (editForm.value?.local_name || '')
})

watch(
  () => route.query,
  async (query) => {
    if (query.kind) kind.value = String(query.kind)
    highlightPid.value = query.pid ? String(query.pid) : ''
    await load()
    if (highlightPid.value) {
      await nextTick()
      const el = document.querySelector('.highlight-row')
      el && el.scrollIntoView({ block: 'center' })
    }
  },
  { immediate: true }
)

async function locatePid(pid) {
  kind.value = 'ontology_proposal'
  highlightPid.value = pid
  await load()
  await nextTick()
  const el = document.querySelector('.highlight-row')
  if (el) {
    el.scrollIntoView({ block: 'center' })
    ElMessage.success('已定位并高亮目标提案')
    return true
  }
  ElMessage.warning('目标提案已不存在或已被处理')
  return false
}

function rowClass({ row }) {
  return row.pid === highlightPid.value ? 'highlight-row' : ''
}

async function load() {
  items.value = await api.get('/api/v1/pending?limit=5000')
  const ontologyItems = items.value.filter((i) => i.kind === 'ontology_proposal')
  if (ontologyItems.length) {
    const corpusIds = [...new Set(ontologyItems.map((i) => i.corpus_id))]
    const labels = []
    for (const cid of corpusIds) {
      try {
        const ont = await api.get(`/api/v1/ontology/${cid}`)
        ont.classes.forEach((c) => labels.push(c.label_zh))
      } catch (err) {
        /* corpus may be gone */
      }
    }
    classLabels.value = [...new Set(labels)].filter(Boolean)
  }
}

async function resolve(row, action) {
  try {
    const resp = await api.post(`/api/v1/pending/${row.pid}/resolve`, { action })
    if (resp.eid) {
      ElMessage.success(`已确认，实体 ${resp.eid} 锚点 ${resp.anchor_count} 个`)
    } else if (resp.error) {
      ElMessage.warning(`未能建立：${resp.error}`)
      if (resp.pending_pids && resp.pending_pids.length) {
        const target = resp.pending_pids[0]
        try {
          await ElMessageBox.confirm(
            `未确认的类提案「${target.label}」存在，是否跳转定位到该提案？`,
            '定位未确认类提案',
            { confirmButtonText: '跳转', cancelButtonText: '留在本页', type: 'warning' }
          )
          router.replace({ path: '/pending', query: { corpus_id: row.corpus_id, kind: 'ontology_proposal', pid: target.pid } })
          await locatePid(target.pid)
        } catch (err) {
          /* 用户取消跳转 */
        }
      }
    } else {
      ElMessage.success(`已${action === 'reject' ? '拒绝' : '处理'}`)
    }
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

function openEdit(row) {
  editFor.value = row
  editForm.value = {
    element_kind: row.payload.element_kind,
    local_name: row.payload.local_name,
    label: row.payload.label,
    definition: row.payload.definition,
    aliases_text: (row.payload.aliases || []).join(','),
    domain: row.payload.domain || '',
    range: row.payload.range || '',
    iri_preview: row.payload.iri_preview || '',
  }
  editDialog.value = true
}

async function saveEdit() {
  try {
    const body = {
      local_name: editForm.value.local_name,
      label: editForm.value.label,
      definition: editForm.value.definition,
      aliases: editForm.value.aliases_text
        ? editForm.value.aliases_text.split(',').map((s) => s.trim()).filter(Boolean)
        : [],
    }
    if (editForm.value.element_kind === 'object_property') {
      body.domain = editForm.value.domain
      body.range = editForm.value.range
    }
    if (editForm.value.element_kind === 'datatype_property') {
      body.domain = editForm.value.domain
      body.range = editForm.value.range
    }
    await api.patch(`/api/v1/pending/${editFor.value.pid}`, body)
    editDialog.value = false
    ElMessage.success('已保存，可以再次点击确认')
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function doRetype() {
  try {
    await api.post(`/api/v1/pending/${retypeFor.value.pid}/resolve`, {
      action: 'retype',
      new_class_iri: retypeIri.value
    })
    retypeDialog.value = false
    retypeIri.value = ''
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

:deep(.highlight-row) {
  background-color: #ecf5ff !important;
}
</style>
