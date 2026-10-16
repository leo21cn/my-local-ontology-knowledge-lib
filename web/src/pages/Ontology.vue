<template>
  <div>
    <el-button style="margin-bottom: 12px" @click="exportTtl">导出 TTL</el-button>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="类" name="classes">
        <div style="margin-bottom: 10px; display: flex; gap: 8px">
          <el-button type="primary" @click="showClass = true">新建类</el-button>
          <el-input v-model="classQuery" placeholder="按中文标签或本地名筛选" clearable style="width: 300px" />
        </div>
        <el-table :data="filteredClasses" border>
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
      </el-tab-pane>

      <el-tab-pane label="对象属性" name="object_properties">
        <div style="margin-bottom: 10px; display: flex; gap: 8px">
          <el-button type="primary" @click="showObjProp = true">新建对象属性</el-button>
          <el-input v-model="objQuery" placeholder="按中文标签或本地名筛选" clearable style="width: 300px" />
        </div>
        <el-table :data="filteredObjProps" border>
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
      </el-tab-pane>

      <el-tab-pane label="数据属性" name="datatype_properties">
        <div style="margin-bottom: 10px; display: flex; gap: 8px">
          <el-button type="primary" @click="showDataProp = true">新建数据属性</el-button>
          <el-input v-model="dataQuery" placeholder="按中文标签或本地名筛选" clearable style="width: 300px" />
        </div>
        <el-table :data="filteredDataProps" border>
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
      </el-tab-pane>
    </el-tabs>

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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const ontology = ref({ classes: [], object_properties: [], datatype_properties: [] })
const activeTab = ref('classes')
const classQuery = ref('')
const objQuery = ref('')
const dataQuery = ref('')
const showClass = ref(false)
const showObjProp = ref(false)
const showDataProp = ref(false)
const editing = ref(false)
const parentText = ref('')
const aliasText = ref('')

function matches(row, query) {
  if (!query) return true
  const needle = query.trim().toLowerCase()
  return (
    (row.label_zh || '').toLowerCase().includes(needle) ||
    (row.iri || '').split('#').pop().toLowerCase().includes(needle)
  )
}

const filteredClasses = computed(() => ontology.value.classes.filter((r) => matches(r, classQuery.value)))
const filteredObjProps = computed(() => ontology.value.object_properties.filter((r) => matches(r, objQuery.value)))
const filteredDataProps = computed(() => ontology.value.datatype_properties.filter((r) => matches(r, dataQuery.value)))

const classForm = reactive({ iri: '', prefix_local: '', label_zh: '', definition: '' })
const objPropForm = reactive({ iri: '', prefix_local: '', label_zh: '', definition: '', domain_iri: '', range_iri: '' })
const dataPropForm = reactive({ iri: '', prefix_local: '', label_zh: '', definition: '', domain_iri: '', xsd_range: 'http://www.w3.org/2001/XMLSchema#string' })

onMounted(load)

async function load() {
  ontology.value = await api.get(`/api/v1/ontology/${id}`)
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
