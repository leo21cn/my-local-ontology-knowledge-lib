<template>
  <div>
    <el-button type="primary" @click="dialog = true">新建库</el-button>
    <el-table class="corpus-table" :data="corpora" border style="margin-top: 12px">
      <el-table-column width="44">
        <template #default>
          <span class="drag-handle" style="cursor: grab; color: #909399; font-size: 16px">⠿</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="subdir" label="子目录" />
      <el-table-column prop="embedding_model" label="模型" />
      <el-table-column prop="vector_dim" label="维度" />
      <el-table-column prop="graph_expand_enabled" label="图谱扩展" width="90">
        <template #default="{ row }">
          <el-tag :type="row.graph_expand_enabled ? 'success' : 'info'">
            {{ row.graph_expand_enabled ? '开' : '关' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="archived" label="归档" width="90">
        <template #default="{ row }">
          <el-tag
            :type="row.archived ? 'warning' : 'info'"
            style="cursor: pointer"
            @click="toggleArchive(row)"
          >{{ row.archived ? '已归档' : '未归档' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="300">
        <template #default="{ row }">
          <div style="margin-bottom: 4px">
            <el-button size="small" @click="$router.push(`/corpora/${row.corpus_id}`)">详情</el-button>
            <el-button size="small" @click="$router.push(`/corpora/${row.corpus_id}/llm`)">LLM辅助建模</el-button>
            <el-button size="small" @click="$router.push(`/ontology/${row.corpus_id}`)">本体</el-button>
          </div>
          <div>
            <el-button size="small" @click="$router.push(`/entities/${row.corpus_id}`)">实体</el-button>
            <el-button size="small" @click="$router.push(`/graph/${row.corpus_id}`)">图谱</el-button>
            <el-button size="small" @click="$router.push(`/stats/${row.corpus_id}`)">统计</el-button>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="删除" width="90">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新建库" width="520px">
      <el-form :model="form" label-width="140px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="权威源子目录"><el-input v-model="form.subdir" /></el-form-item>
        <el-form-item label="本体前缀"><el-input v-model="form.ontology_prefix" /></el-form-item>
        <el-form-item label="嵌入模型"><el-input v-model="form.embedding_model" /></el-form-item>
        <el-form-item label="向量维度"><el-input-number v-model="form.vector_dim" :min="1" /></el-form-item>
        <el-form-item label="切片上限"><el-input-number v-model="form.chunk_max_chars" :min="1" /></el-form-item>
        <el-form-item label="重叠字符"><el-input-number v-model="form.chunk_overlap" :min="0" /></el-form-item>
        <el-form-item label="图谱扩展">
          <el-switch v-model="form.graph_expand_enabled" />
        </el-form-item>
        <el-form-item label="图谱权重"><el-input-number v-model="form.graph_weight" :min="0" :step="0.1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Sortable from 'sortablejs'
import { api } from '../api'

const corpora = ref([])
const dialog = ref(false)
let sortable = null
const form = reactive({
  name: '', subdir: '', ontology_prefix: '', embedding_model: 'text-embedding-v4',
  vector_dim: 1024, chunk_max_chars: 700, chunk_overlap: 60,
  graph_expand_enabled: true, graph_weight: 1.0
})

onMounted(load)

async function load() {
  corpora.value = await api.get('/api/v1/corpora')
  await initSortable()
}

async function initSortable() {
  await nextTick()
  if (sortable) sortable.destroy()
  const tbody = document.querySelector('.corpus-table .el-table__body tbody')
  if (!tbody) return
  sortable = Sortable.create(tbody, {
    handle: '.drag-handle',
    animation: 150,
    onEnd: async (evt) => {
      if (evt.oldIndex === evt.newIndex) return
      const moved = corpora.value.splice(evt.oldIndex, 1)[0]
      corpora.value.splice(evt.newIndex, 0, moved)
      try {
        await api.post('/api/v1/corpora/order', { ids: corpora.value.map((c) => c.corpus_id) })
        ElMessage.success('顺序已保存')
      } catch (err) {
        ElMessage.error(err.message)
      }
      await load()
    }
  })
}

async function create() {
  try {
    await api.post('/api/v1/corpora', { ...form })
    dialog.value = false
    ElMessage.success('已创建')
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(`删除库「${row.name}」将级联删除索引与本体数据，权威源文件不受影响。确认？`, '二次确认', { type: 'warning' })
    await api.del(`/api/v1/corpora/${row.corpus_id}`)
    await load()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.message)
  }
}

async function toggleArchive(row) {
  try {
    await api.patch(`/api/v1/corpora/${row.corpus_id}`, { archived: !row.archived })
    ElMessage.success(row.archived ? '已取消归档，恢复轮询与检索' : '已归档：停止轮询同步，检索跳过该库')
    await load()
  } catch (err) {
    ElMessage.error(err.message)
  }
}
</script>
