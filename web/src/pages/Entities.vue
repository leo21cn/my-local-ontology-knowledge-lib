<template>
  <div>
    <el-button type="primary" style="margin-bottom: 12px" @click="showCreate = true">新建实体</el-button>
    <el-button style="margin-bottom: 12px" @click="showRelation = true">新建关系</el-button>
    <el-button style="margin-bottom: 12px" :disabled="selected.length !== 2" @click="merge">合并所选</el-button>
    <el-button style="margin-bottom: 12px" :disabled="selected.length !== 1" @click="showSplit = true">拆分所选</el-button>

    <el-table :data="entities" border @selection-change="(rows) => (selected = rows)"
              @expand-change="(row, expanded) => expanded && loadRelations(row)">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div v-if="!relationMap[row.eid] || relationMap[row.eid].loading" style="padding: 6px 12px; color: #909399">
            加载关系中…
          </div>
          <div v-else-if="!relationMap[row.eid].items.length" style="padding: 6px 12px; color: #909399">
            该实体暂无已确认关系
          </div>
          <el-table v-else :data="relationMap[row.eid].items" size="small" border style="margin: 6px 12px; width: auto">
            <el-table-column label="方向" width="70">
              <template #default="{ row: r }">
                <el-tag size="small" :type="r.direction === '出' ? 'success' : 'warning'">{{ r.direction }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="type_label" label="关系属性" />
            <el-table-column prop="other_label" label="对方实体" />
            <el-table-column prop="state" label="状态" width="100" />
          </el-table>
        </template>
      </el-table-column>
      <el-table-column type="selection" width="50" />
      <el-table-column prop="label" label="名称" />
      <el-table-column prop="class_iri" label="类 IRI" show-overflow-tooltip />
      <el-table-column label="锚点数" width="90">
        <template #default="{ row }">{{ (row.anchors || []).length }}</template>
      </el-table-column>
      <el-table-column label="锚点">
        <template #default="{ row }">
          <el-tag v-for="(a, i) in row.anchors" :key="i" size="small" style="margin-right: 4px">
            {{ a.rel_path }} #{{ a.seq }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" title="新建实体" width="480px">
      <el-form :model="entityForm" label-width="100px">
        <el-form-item label="名称"><el-input v-model="entityForm.label" /></el-form-item>
        <el-form-item label="类 IRI"><el-input v-model="entityForm.class_iri" /></el-form-item>
        <el-form-item label="锚点相对路径"><el-input v-model="entityForm.anchor.rel_path" /></el-form-item>
        <el-form-item label="锚点序号"><el-input-number v-model="entityForm.anchor.seq" :min="0" /></el-form-item>
        <el-form-item label="锚点哈希"><el-input v-model="entityForm.anchor.sha256" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createEntity">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showRelation" title="新建关系" width="480px">
      <el-form :model="relationForm" label-width="110px">
        <el-form-item label="起点 eid"><el-input v-model="relationForm.from_eid" /></el-form-item>
        <el-form-item label="终点 eid"><el-input v-model="relationForm.to_eid" /></el-form-item>
        <el-form-item label="对象属性 IRI"><el-input v-model="relationForm.type_iri" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRelation = false">取消</el-button>
        <el-button type="primary" @click="createRelation">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showSplit" title="拆分实体" width="520px">
      <el-form label-width="110px">
        <el-form-item label="新名称"><el-input v-model="splitForm.new_label" /></el-form-item>
        <el-form-item label="类 IRI">
          <el-input v-model="splitForm.class_iri" :placeholder="selected[0]?.class_iri || '默认沿用源实体类'" />
        </el-form-item>
        <el-form-item label="拆出的锚点">
          <el-checkbox-group v-model="splitForm.anchors">
            <el-checkbox v-for="(a, i) in selected[0]?.anchors || []" :key="i" :value="a" style="display: block">
              {{ a.rel_path }} #{{ a.seq }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSplit = false">取消</el-button>
        <el-button type="primary" @click="split">拆分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const entities = ref([])
const selected = ref([])
const relationMap = ref({})
const showCreate = ref(false)
const showRelation = ref(false)
const showSplit = ref(false)

const entityForm = reactive({ label: '', class_iri: '', anchor: { rel_path: '', seq: 0, sha256: '' } })
const relationForm = reactive({ from_eid: '', to_eid: '', type_iri: '' })
const splitForm = reactive({ new_label: '', class_iri: '', anchors: [] })

onMounted(load)

async function load() {
  entities.value = await api.get(`/api/v1/entities?corpus_id=${id}`)
}

async function loadRelations(row) {
  if (relationMap.value[row.eid]) return
  relationMap.value[row.eid] = { loading: true, items: [] }
  try {
    const data = await api.get(`/api/v1/graph?entity_id=${row.eid}&depth=1`)
    const nodeMap = Object.fromEntries(data.nodes.map((n) => [n.eid, n.label]))
    relationMap.value[row.eid] = {
      loading: false,
      items: data.edges.map((e) => {
        const isOut = e.from === row.eid
        return {
          direction: isOut ? '出' : '入',
          type_label: (e.type_iri || '').split('#').pop(),
          other_label: nodeMap[isOut ? e.to : e.from] || '?',
          state: e.state,
        }
      })
    }
  } catch (err) {
    relationMap.value[row.eid] = { loading: false, items: [] }
    ElMessage.error(err.message)
  }
}

async function createEntity() {
  try {
    await api.post(`/api/v1/entities?corpus_id=${id}`, { ...entityForm })
    showCreate.value = false
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function createRelation() {
  try {
    const resp = await api.post('/api/v1/relations', { ...relationForm })
    if (resp.created) {
      ElMessage.success('关系已建立')
      showRelation.value = false
    } else {
      ElMessage.warning(`违反本体定义（${resp.violations.join('、')}），已转待处理队列 ${resp.pending_pid}`)
      showRelation.value = false
    }
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function merge() {
  try {
    await ElMessageBox.confirm(
      `将「${selected.value[1].label}」合并进「${selected.value[0].label}」？被合并实体的锚点与关系并入留存实体。`,
      '合并确认',
      { type: 'warning' }
    )
    const resp = await api.post('/api/v1/entities/merge', {
      keep: selected.value[0].eid,
      drop: selected.value[1].eid
    })
    ElMessage.success(`合并完成，留存实体锚点 ${resp.anchors} 个`)
    await load()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  }
}

async function split() {
  try {
    if (!splitForm.new_label || !splitForm.anchors.length) {
      ElMessage.error('请填写新名称并至少选择一个锚点')
      return
    }
    const payload = {
      eid: selected.value[0].eid,
      new_label: splitForm.new_label,
      class_iri: splitForm.class_iri || undefined,
      anchors: splitForm.anchors
    }
    const resp = await api.post('/api/v1/entities/split', payload)
    ElMessage.success(`拆分完成：原实体剩 ${resp.src_anchors} 个锚点，新实体 ${resp.new_anchors} 个`)
    showSplit.value = false
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}
</script>
