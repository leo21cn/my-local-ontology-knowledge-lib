<template>
  <div>
    <el-tabs v-model="kind">
      <el-tab-pane label="实体提案" name="proposal" />
      <el-tab-pane label="关系提案" name="relation_proposal" />
      <el-tab-pane label="校验违规" name="violation" />
      <el-tab-pane label="嵌入失败" name="embed_failed" />
      <el-tab-pane label="抽取失败" name="extract_failed" />
    </el-tabs>

    <el-table :data="grouped" border>
      <el-table-column prop="pid" label="ID" width="260" show-overflow-tooltip />
      <el-table-column label="摘要">
        <template #default="{ row }">
          <pre style="white-space: pre-wrap; margin: 0">{{ JSON.stringify(row.payload, null, 2) }}</pre>
        </template>
      </el-table-column>
      <el-table-column prop="attempts" label="尝试次数" width="100" />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button v-if="['proposal', 'relation_proposal'].includes(row.kind)" size="small" type="primary" @click="resolve(row, 'confirm')">确认</el-button>
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
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const items = ref([])
const kind = ref('proposal')
const retypeDialog = ref(false)
const retypeFor = ref(null)
const retypeIri = ref('')

const grouped = computed(() => items.value.filter((i) => i.kind === kind.value))

onMounted(load)

async function load() {
  items.value = await api.get('/api/v1/pending')
}

async function resolve(row, action) {
  try {
    const resp = await api.post(`/api/v1/pending/${row.pid}/resolve`, { action })
    if (resp.eid) {
      ElMessage.success(`已确认，实体 ${resp.eid} 锚点 ${resp.anchor_count} 个`)
    } else if (resp.error) {
      ElMessage.warning(`未能建立：${resp.error}`)
    } else {
      ElMessage.success(`已${action === 'reject' ? '拒绝' : '处理'}`)
    }
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
