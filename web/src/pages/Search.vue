<template>
  <div>
    <el-form inline>
      <el-form-item label="库">
        <el-select v-model="form.corpus_id" style="width: 200px">
          <el-option v-for="c in corpora" :key="c.corpus_id" :label="c.name" :value="c.corpus_id" />
        </el-select>
      </el-form-item>
      <el-form-item label="查询">
        <el-input v-model="form.query" style="width: 360px" @keyup.enter="run" />
      </el-form-item>
      <el-form-item label="条数">
        <el-input-number v-model="form.top_k" :min="1" :max="50" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="run">检索</el-button>
      </el-form-item>
    </el-form>

    <el-form inline>
      <el-form-item label="标签过滤">
        <el-input v-model="tags" placeholder="逗号分隔" style="width: 200px" />
      </el-form-item>
      <el-form-item label="类型过滤">
        <el-input v-model="classIri" placeholder="类 IRI，留空不过滤" style="width: 300px" />
      </el-form-item>
    </el-form>

    <el-table :data="results" border>
      <el-table-column prop="fused_rank" label="融合排名" width="90" />
      <el-table-column prop="vector_rank" label="向量排名" width="90" />
      <el-table-column prop="score" label="分数" width="90" />
      <el-table-column label="命中片段">
        <template #default="{ row }">
          <div>{{ row.content }}</div>
          <el-tag size="small">{{ row.asset_rel_path }} #{{ row.anchor.seq }}</el-tag>
          <el-tag v-for="h in row.heading_path" :key="h" size="small" type="info">{{ h }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上下文">
        <template #default="{ row }">
          <el-popover width="520" trigger="click">
            <template #reference><el-link>展开</el-link></template>
            <pre style="white-space: pre-wrap">{{ row.context }}</pre>
          </el-popover>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const corpora = ref([])
const results = ref([])
const loading = ref(false)
const tags = ref('')
const classIri = ref('')
const form = ref({ corpus_id: '', query: '', top_k: 10 })

onMounted(async () => {
  corpora.value = await api.get('/api/v1/corpora')
  if (!form.value.corpus_id && corpora.value.length) {
    form.value.corpus_id = corpora.value[0].corpus_id
  }
})

async function run() {
  loading.value = true
  try {
    results.value = await api.post('/api/v1/search', {
      ...form.value,
      filters: {
        tags: tags.value ? tags.value.split(',').map((t) => t.trim()) : [],
        class_iri: classIri.value.trim() || undefined
      }
    })
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}
</script>
