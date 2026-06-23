<template>
  <div class="app-container">
    <header class="app-header">
      <h1 @click="$router.push('/')">格式合同智能审查系统 Demo</h1>
      <nav>
        <router-link to="/">模板管理</router-link>
        <router-link to="/review">审查工作台</router-link>
      </nav>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
.app-container { min-height: 100vh; background: #f0f2f5; }
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 24px; background: #fff; border-bottom: 1px solid #e4e7ed;
}
.app-header h1 { font-size: 18px; cursor: pointer; }
.app-header nav a { margin-left: 16px; text-decoration: none; color: #409eff; }
.app-main { padding: 24px; max-width: 1400px; margin: 0 auto; }
</style>
