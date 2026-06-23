<template>
  <div class="app-shell">
    <header class="app-bar">
      <div class="bar-left" @click="$router.push('/')">
        <span class="logo-mark">契</span>
        <span class="logo-text">合同智能审查系统</span>
      </div>
      <nav class="bar-nav">
        <router-link to="/" class="nav-link">模板管理</router-link>
        <router-link to="/review" class="nav-link">审查工作台</router-link>
      </nav>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
@import './assets/tokens.css';

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--font-body);
  font-size: var(--text-base);
  color: var(--ink);
  background: var(--paper);
  -webkit-font-smoothing: antialiased;
}

/* ---- App bar ---- */
.app-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 var(--space-5);
  background: var(--paper-white);
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}
.bar-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  cursor: pointer;
  user-select: none;
}
.logo-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--vermilion);
  border: 2px solid var(--vermilion);
  border-radius: var(--radius-sm);
}
.logo-text {
  font-family: var(--font-display);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--ink);
  letter-spacing: .02em;
}
.bar-nav {
  display: flex;
  gap: var(--space-1);
}
.nav-link {
  padding: 6px 14px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--ink-soft);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition: background .15s, color .15s;
}
.nav-link:hover { background: var(--paper-hover); color: var(--ink); }
.nav-link.router-link-active { color: var(--vermilion); background: var(--vermilion-soft); }

/* ---- Main ---- */
.app-main {
  height: calc(100vh - 52px);
  overflow: hidden;
}

/* ---- Global Element Plus overrides ---- */
.el-button--primary {
  --el-button-bg-color: var(--ink);
  --el-button-border-color: var(--ink);
  --el-button-hover-bg-color: #333;
  --el-button-hover-border-color: #333;
}
.el-button--danger {
  --el-button-bg-color: var(--vermilion);
  --el-button-border-color: var(--vermilion);
  --el-button-hover-bg-color: #a01830;
  --el-button-hover-border-color: #a01830;
}
.el-tag--danger {
  --el-tag-bg-color: var(--vermilion-soft);
  --el-tag-border-color: var(--vermilion-border);
  --el-tag-text-color: var(--vermilion);
}
.el-tag--success {
  --el-tag-bg-color: var(--ink-green-soft);
  --el-tag-border-color: var(--ink-green-border);
  --el-tag-text-color: var(--ink-green);
}
.el-tag--warning {
  --el-tag-bg-color: var(--amber-soft);
  --el-tag-border-color: var(--amber-border);
  --el-tag-text-color: var(--amber);
}
.el-table th.el-table__cell {
  background: var(--paper-warm);
  color: var(--ink-soft);
  font-size: var(--text-sm);
  font-weight: 600;
  border-color: var(--rule);
}
.el-table td.el-table__cell { border-color: var(--rule-light); }
.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell {
  background: var(--paper-warm);
}
.el-card {
  border-color: var(--rule);
  box-shadow: var(--shadow-sm);
}
.el-card__header {
  border-color: var(--rule);
  background: var(--paper-warm);
}
.el-input__wrapper, .el-select .el-input__wrapper {
  box-shadow: 0 0 0 1px var(--rule) inset;
}
.el-input__wrapper:hover, .el-select .el-input__wrapper:hover {
  box-shadow: 0 0 0 1px var(--ink-muted) inset;
}
</style>
