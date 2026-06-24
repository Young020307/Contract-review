<template>
  <div class="app-shell">
    <header class="app-bar">
      <div class="bar-left" @click="$router.push('/')">
        <span class="logo-mark">契</span>
        <span class="logo-text">合同智能审查系统</span>
      </div>
      <nav class="bar-nav">
        <router-link to="/" class="nav-link">
          <el-icon class="nav-icon"><Document /></el-icon>
          模板管理
        </router-link>
        <router-link to="/review" class="nav-link">
          <el-icon class="nav-icon"><Search /></el-icon>
          审查工作台
        </router-link>
      </nav>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { Document, Search } from '@element-plus/icons-vue'
</script>

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
  height: 56px;
  padding: 0 var(--space-5);
  background: var(--paper-white);
  border-bottom: 1px solid var(--rule);
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
  flex-shrink: 0;
  position: relative;
  z-index: 100;
}
.app-bar::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--primary), var(--amber), var(--ink-green));
  opacity: .5;
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
  width: 34px;
  height: 34px;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 700;
  color: var(--paper-white);
  background: var(--primary);
  border-radius: var(--radius-md);
  box-shadow: 0 2px 6px rgba(196,30,58,.25);
}
.logo-text {
  font-family: var(--font-display);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--ink);
  letter-spacing: .03em;
}
.bar-nav {
  display: flex;
  gap: var(--space-2);
}
.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--ink-soft);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}
.nav-icon { font-size: 15px; }
.nav-link:hover { background: var(--paper-hover); color: var(--ink); }
.nav-link.router-link-active {
  color: var(--primary);
  background: var(--primary-soft);
  box-shadow: inset 0 -2px 0 var(--primary);
}

/* ---- Main ---- */
.app-main {
  height: calc(100vh - 56px);
  overflow: hidden;
}

/* ---- Global Element Plus overrides ---- */
.el-button {
  --el-button-border-radius: var(--radius-md);
  --el-button-font-weight: 500;
}
.el-button--primary {
  --el-button-bg-color: var(--ink);
  --el-button-border-color: var(--ink);
  --el-button-hover-bg-color: #333;
  --el-button-hover-border-color: #333;
}
.el-button--danger {
  --el-button-bg-color: var(--danger);
  --el-button-border-color: var(--danger);
  --el-button-hover-bg-color: #b91c1c;
  --el-button-hover-border-color: #b91c1c;
}
.el-button--primary.is-plain {
  --el-button-text-color: var(--ink);
  --el-button-border-color: var(--ink);
}
.el-tag {
  --el-tag-border-radius: var(--radius-sm);
}
.el-tag--danger {
  --el-tag-bg-color: var(--danger-soft);
  --el-tag-border-color: var(--danger-border);
  --el-tag-text-color: var(--danger);
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
.el-table {
  --el-table-border-radius: var(--radius-md);
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
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.el-card__header {
  border-color: var(--rule);
  background: var(--paper-warm);
}
.el-input__wrapper, .el-select .el-input__wrapper {
  border-radius: var(--radius-md);
  box-shadow: 0 0 0 1px var(--rule) inset;
  transition: all var(--transition-fast);
}
.el-input__wrapper:hover, .el-select .el-input__wrapper:hover {
  box-shadow: 0 0 0 1px var(--ink-muted) inset;
}
.el-select .el-input__wrapper.is-focus {
  box-shadow: 0 0 0 1px var(--ink) inset;
}
.el-radio__input.is-checked .el-radio__inner {
  background: var(--ink);
  border-color: var(--ink);
}
.el-radio__input.is-checked + .el-radio__label {
  color: var(--ink);
}
.el-popconfirm .el-button--primary {
  --el-button-bg-color: var(--danger);
  --el-button-border-color: var(--danger);
}
</style>
