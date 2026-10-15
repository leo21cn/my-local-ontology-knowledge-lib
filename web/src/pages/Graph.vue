<template>
  <div>
    <el-form inline>
      <el-form-item label="实体">
        <el-select v-model="entityId" filterable style="width: 320px" placeholder="选择实体">
          <el-option v-for="e in entities" :key="e.eid" :label="e.label" :value="e.eid" />
        </el-select>
      </el-form-item>
      <el-form-item label="深度">
        <el-radio-group v-model="depth" @change="loadGraph">
          <el-radio-button :value="1">1 跳</el-radio-button>
          <el-radio-button :value="2">2 跳</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="loadGraph">展开</el-button>
      </el-form-item>
    </el-form>
    <div ref="container" style="height: 560px; border: 1px solid #dcdfe6"></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const container = ref(null)
const entityId = ref('')
const entities = ref([])
const depth = ref(2)
let network = null

const palette = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#9C27B0', '#00BCD4', '#FF9800']

function colorFor(classIri) {
  let hash = 0
  for (const ch of classIri || '') hash = (hash * 31 + ch.charCodeAt(0)) % 997
  return palette[hash % palette.length]
}

onMounted(async () => {
  entities.value = await api.get(`/api/v1/entities?corpus_id=${id}`)
  if (entities.value.length) entityId.value = entities.value[0].eid
})

async function loadGraph() {
  if (!entityId.value) return
  const data = await api.get(`/api/v1/graph?entity_id=${entityId.value}&depth=${depth.value}`)
  const nodes = new DataSet(data.nodes.map((n) => ({ id: n.eid, label: n.label, color: colorFor(n.class_iri) })))
  const edges = new DataSet(data.edges.map((e) => ({ from: e.from, to: e.to, label: e.type_iri.split('#').pop() })))
  if (!network) {
    network = new Network(container.value, { nodes, edges }, { interaction: { dragNodes: false }, physics: { enabled: false } })
  } else {
    network.setData({ nodes, edges })
  }
}
</script>
