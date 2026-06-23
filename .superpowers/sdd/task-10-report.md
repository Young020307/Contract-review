### Task 10 Report: Frontend scaffold

**Status:** Complete

**Created files:**

| File | Purpose |
|------|---------|
| `frontend/package.json` | Node.js project config with Vue 3, Element Plus, Monaco, Axios |
| `frontend/index.html` | HTML entry point (zh-CN) |
| `frontend/vite.config.ts` | Vite config with Vue plugin, Monaco editor plugin, API proxy to :8000 |
| `frontend/tsconfig.json` | TypeScript config (ES2020, strict, bundler resolution) |
| `frontend/env.d.ts` | Type declarations for .vue modules |
| `frontend/src/main.ts` | App entry — mounts Vue with Element Plus and router |
| `frontend/src/App.vue` | Root component with header, nav, and router-view |
| `frontend/src/router/index.ts` | Vue Router with 3 routes: template list, annotation workbench, review |
| `frontend/src/types/index.ts` | All shared TypeScript interfaces |
| `frontend/src/api/index.ts` | Axios-based API client with typed functions for all endpoints |
| `frontend/src/views/TemplateList.vue` | Placeholder view (Task 11) |
| `frontend/src/views/AnnotationWorkbench.vue` | Placeholder view (Task 12) |
| `frontend/src/views/ReviewWorkbench.vue` | Placeholder view (Task 13) |

**Verification:**
- `npm install` completed successfully (171 packages)
- `vite-plugin-monaco-editor` installed as devDependency
- `npm run dev` starts Vite on http://localhost:5173 without errors
- Proxy forwards `/api` requests to `http://localhost:8000`

**Routes:**
- `/` — TemplateList (lazy-loaded)
- `/annotate/:id` — AnnotationWorkbench (lazy-loaded, props: true)
- `/review` — ReviewWorkbench (lazy-loaded)
