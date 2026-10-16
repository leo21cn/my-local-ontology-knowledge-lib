<template>
  <div>
    <el-form inline>
      <el-form-item label="模式">
        <el-radio-group v-model="mode" @change="resetView">
          <el-radio-button value="all">全部视图</el-radio-button>
          <el-radio-button value="center">中心实体</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <template v-if="mode === 'center'">
        <el-form-item label="实体">
          <el-select v-model="entityId" filterable style="width: 320px" placeholder="选择实体">
            <el-option v-for="e in entities" :key="e.eid" :label="e.label" :value="e.eid" />
          </el-select>
        </el-form-item>
        <el-form-item label="深度">
          <el-radio-group v-model="depth">
            <el-radio-button :value="1">1 跳</el-radio-button>
            <el-radio-button :value="2">2 跳</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="resetView">展开</el-button>
        </el-form-item>
      </template>
      <el-form-item v-else>
        <el-button @click="resetView">重新加载</el-button>
      </el-form-item>
      <el-form-item>
        <el-button @click="resetView">重置</el-button>
      </el-form-item>
    </el-form>
    <el-alert
      v-if="truncated"
      type="warning"
      :closable="false"
      style="margin-bottom: 8px"
      :title="`实体较多：已显示前 500 个（共 ${total} 个），其余未展示`"
    />
    <div style="color: #909399; font-size: 12px; margin-bottom: 6px">
      点击节点展开其下一级关系（可逐级下钻），滚轮缩放画布，拖动空白处平移
    </div>
    <div ref="container" style="height: 560px; border: 1px solid #dcdfe6"></div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Network } from 'vis-network'
import { DataSet } from 'vis-data'
import { api } from '../api'

const route = useRoute()
const id = route.params.id
const container = ref(null)
const mode = ref('all')
const entityId = ref('')
const entities = ref([])
const depth = ref(1)
const truncated = ref(false)
const total = ref(0)
let network = null
let nodeSet = new DataSet([])
let edgeSet = new DataSet([])
const expanded = new Set()

const palette = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#909399', '#9C27B0', '#00BCD4', '#FF9800']

function colorFor(classIri) {
  let hash = 0
  for (const ch of classIri || '') hash = (hash * 31 + ch.charCodeAt(0)) % 997
  return palette[hash % palette.length]
}

function ensureNetwork() {
  if (network) return
  const options = {
    interaction: { dragNodes: false },
    physics: { enabled: false }
  }
  network = new Network(container.value, { nodes: nodeSet, edges: edgeSet }, options)
  network.on('click', (params) => {
    if (params.nodes.length) expandNode(params.nodes[0])
  })
}

function mergeData(nodes, edges) {
  nodeSet.update(
    nodes.map((n) => ({ id: n.eid, label: n.label, color: colorFor(n.class_iri) }))
  )
  edgeSet.update(
    edges.map((e) => ({ from: e.from, to: e.to, label: (e.type_iri || '').split('#').pop() }))
  )
}

function centerOnAll() {
  const options = { physics: { enabled: true, stabilization: { iterations: 120 } } }
  network.setOptions(options)
  network.once('stabilizationIterationsDone', () => {
    network.setOptions({ physics: { enabled: false } })
  })
}

async function resetView() {
  nodeSet = new DataSet([])
  edgeSet = new DataSet([])
  expanded.clear()
  truncated.value = false
  total.value = 0
  ensureNetwork()
  network.setData({ nodes: nodeSet, edges: edgeSet })
  if (mode.value === 'all') {
    const data = await api.get(`/api/v1/graph?mode=all&corpus_id=${id}`)
    truncated.value = data.truncated
    total.value = data.total
    mergeData(data.nodes, data.edges)
    if (data.nodes.length) centerOnAll()
  } else {
    if (!entityId.value) {
      ElMessage.warning('请选择实体')
      return
    }
    const data = await api.get(`/api/v1/graph?entity_id=${entityId.value}&depth=${depth.value}`)
    mergeData(data.nodes, data.edges)
  }
}

async function expandNode(eid) {
  if (expanded.has(eid)) {
    ElMessage.info('该节点已展开')
    return
  }
  expanded.add(eid)
  const data = await api.get(`/api/v1/graph?entity_id=${eid}&depth=1`)
  const beforeNodes = nodeSet.length
  const beforeEdges = edgeSet.length
  mergeData(data.nodes, data.edges)
  if (nodeSet.length === beforeNodes && edgeSet.length === beforeEdges) {
    ElMessage.info('该节点没有更多相邻关系')
  }
}

onMounted(async () => {
  entities.value = await api.get(`/api/v1/entities?corpus_id=${id}`)
  if (entities.value.length) entityId.value = entities.value[0].eid
  await resetView()
})
</script>
