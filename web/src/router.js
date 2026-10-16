import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/corpora' },
  { path: '/corpora', name: 'corpora', component: () => import('./pages/Corpora.vue') },
  { path: '/corpora/:id', name: 'corpus', component: () => import('./pages/CorpusDetail.vue') },
  { path: '/corpora/:id/llm', name: 'llm', component: () => import('./pages/LlmModeling.vue') },
  { path: '/corpora/:id/chunks', name: 'chunks', component: () => import('./pages/Chunks.vue') },
  { path: '/search', name: 'search', component: () => import('./pages/Search.vue') },
  { path: '/ontology/:id', name: 'ontology', component: () => import('./pages/Ontology.vue') },
  { path: '/entities/:id', name: 'entities', component: () => import('./pages/Entities.vue') },
  { path: '/pending', name: 'pending', component: () => import('./pages/Pending.vue') },
  { path: '/graph/:id', name: 'graph', component: () => import('./pages/Graph.vue') },
  { path: '/stats/:id', name: 'stats', component: () => import('./pages/Stats.vue') }
]

export default createRouter({ history: createWebHistory(), routes })
