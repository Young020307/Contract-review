# Integration API — 统一外部 API 设计

## 目标

为外部系统提供统一的 API 入口（Facade Pattern），暴露全部模板管理、文档上传和审查功能，
并新增一站式审查端点合并上传+比对+校验三步操作。

## 架构变更

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/services/review_service.py` | 审查业务编排：从 `routers/review.py` 提取纯业务逻辑 |
| `backend/routers/integration.py` | 外部 API 路由，前缀 `/api/integration/v1` |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/routers/review.py` | 精简为薄路由层，业务逻辑委托到 `review_service.py` |
| `backend/main.py` | 注册 `integration_router` |

## Service 层：`services/review_service.py`

从 `routers/review.py` 的 `review_compare()` 和 `review_validate()` 中提取纯业务逻辑，
不碰 HTTP 概念（File、UploadFile、Request、HTTPException）。

```python
def run_compare(template_id: int, document_id: int) -> dict:
    # DB 查询 template/doc 路径 → 解析 → 对齐 → 比对 → 返回 CompareResult

def run_validate(template_id: int, document_id: int) -> dict:
    # DB 查询 → 解析 → 提取填充值 → 校验 → checkbox/依赖处理 → 返回 ValidateResult
```

函数签名只接受业务标识符（ID），返回 dict。Service 函数内部自行管理数据库连接
（通过 `get_connection()`），调用方无需传递连接对象。

## 外部 API 路由：`routers/integration.py`

前缀：`/api/integration/v1`

### 端点列表（12 个）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/templates` | 模板列表 |
| POST | `/templates/upload` | 上传模板 |
| GET | `/templates/{id}` | 模板详情 |
| DELETE | `/templates/{id}` | 删除模板 |
| POST | `/templates/{id}/annotations` | 保存标注 |
| GET | `/templates/{id}/annotations` | 获取标注 |
| GET | `/documents/proxy-template/{template_id}` | 代理模板文件下载 |
| POST | `/documents/upload` | 上传待审文档 |
| GET | `/documents/{id}` | 文档详情 |
| POST | `/review/compare` | 比对 |
| POST | `/review/validate` | 校验 |
| POST | `/review/full` | 一站式审查（新增） |

前 11 个端点与现有内部 API 逻辑完全一致，通过调用相同 Service 函数实现，零重复。

### 一站式审查端点

```
POST /api/integration/v1/review/full
Content-Type: multipart/form-data

Parameters:
  template_id: int (required)
  file: .docx (required)
```

路由层流程：

1. 接收文件流 → 保存到磁盘（`temp/` 目录）
2. 写入 `documents` 表 → 获得 `document_id`
3. 调用 `run_compare(template_id, document_id)`
4. 调用 `run_validate(template_id, document_id)`
5. 返回 `{ document_id, compare: CompareResult, validate: ValidateResult }`

文件 I/O 和数据库记录创建是路由层职责，不进入 Service 层。

## 错误处理

- 沿用现有模式：`HTTPException` + 标准 HTTP 状态码
- 路由层校验参数（如 template_id 不存在 → 404），Service 层不抛异常
- 响应格式与现有内部 API 一致（FastAPI 默认 `{"detail": "..."}`），不引入自定义包装

## 文件 I/O 边界

```
Router 层（integration.py / review.py）：
  - 文件保存、路径解析
  - DB 记录创建（产生 ID）
  - 调用 Service 函数
  - 保存 review_task 记录（仅 review 路由）

Service 层（review_service.py / parser.py / diff_engine.py / validator.py）：
  - 通过 ID 查找路径 → 读文件 → 解析 → 计算 → 返回结果
  - 不接收 File/UploadFile 对象
```

## 鉴权

当前不添加鉴权，与内部 API 一致。后续可独立为 integration 路由添加 API-Key 验证。

## 变更范围（不含）

- 前端代码不变
- 数据库 schema 不变
- 现有内部 API 接口不变（向后兼容）
- 测试需新增 `test_integration.py` 覆盖一站式端点
