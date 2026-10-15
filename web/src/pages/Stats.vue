<template>
  <el-row :gutter="12">
    <el-col :span="4"><el-card><div class="label">任务数</div><div class="value">{{ stats.tasks ?? 0 }}</div></el-card></el-col>
    <el-col :span="4"><el-card><div class="label">累计令牌</div><div class="value">{{ stats.tokens ?? 0 }}</div></el-card></el-col>
    <el-col :span="4"><el-card><div class="label">嵌入重试次数</div><div class="value">{{ stats.retries ?? 0 }}</div></el-card></el-col>
    <el-col :span="4"><el-card><div class="label">累计费用估算</div><div class="value">{{ stats.cost ?? 0 }}</div></el-card></el-col>
    <el-col :span="4"><el-card><div class="label">失败任务数</div><div class="value">{{ stats.failed ?? 0 }}</div></el-card></el-col>
    <el-col :span="4"><el-card><div class="label">待处理积压</div><div class="value">{{ stats.pending ?? 0 }}</div></el-card></el-col>
  </el-row>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const stats = ref({})

onMounted(async () => {
  stats.value = await api.get(`/api/v1/stats/corpus/${id}`)
})
</script>

<style scoped>
.label { color: #909399; font-size: 13px; }
.value { font-size: 24px; font-weight: 600; margin-top: 6px; }
</style>
