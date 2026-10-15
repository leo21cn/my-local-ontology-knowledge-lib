<template>
  <el-table :data="assets" border @expand-change="loadChunks">
    <el-table-column type="expand">
      <template #default="{ row }">
        <el-table :data="row.chunks || []" border size="small">
          <el-table-column prop="seq" label="序号" width="70" />
          <el-table-column label="标题路径">
            <template #default="scope">
              <el-tag v-for="h in scope.row.heading_path" :key="h" size="small" type="info" style="margin-right: 4px">{{ h }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="char_len" label="字符数" width="90" />
          <el-table-column prop="chunk_sha256" label="内容哈希" />
          <el-table-column label="正文">
            <template #default="scope">
              <el-popover width="560" trigger="click">
                <template #reference><el-link>查看</el-link></template>
                <pre style="white-space: pre-wrap">{{ scope.row.text }}</pre>
              </el-popover>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-table-column>
    <el-table-column prop="rel_path" label="相对路径" />
    <el-table-column prop="sha256" label="文件哈希" show-overflow-tooltip />
    <el-table-column label="修改时间" width="180">
      <template #default="{ row }">{{ new Date(row.mtime * 1000).toLocaleString() }}</template>
    </el-table-column>
    <el-table-column label="同步状态" width="100">
      <template #default="{ row }">
        <el-tag :type="row.synced ? 'success' : 'danger'">{{ row.synced ? '已同步' : '未同步' }}</el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const assets = ref([])

onMounted(async () => {
  assets.value = await api.get(`/api/v1/corpora/${id}/assets`)
})

async function loadChunks(row) {
  if (!row.chunks) {
    row.chunks = await api.get(`/api/v1/corpora/${id}/assets/${encodeURIComponent(row.rel_path)}/chunks`)
  }
}
</script>
