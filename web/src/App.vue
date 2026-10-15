<template>
  <el-container>
    <el-aside width="180px">
      <el-menu router :default-active="$route.path">
        <el-menu-item index="/corpora">库管理</el-menu-item>
        <el-menu-item index="/search">检索测试</el-menu-item>
        <el-menu-item index="/pending">待处理队列</el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
