# Clew 设计方案（字段级 AI 数据血缘工具；2026-10 起定名 Clew，早期工作名 LineageLite）

> 基于 OpenMetadata 与 DataHub 两个开源方案的调研结论，面向「文件导入 + 字段级源文件定位 + AI 辅助」的轻量级数据血缘工具。
> 文中未确认的业务事实以 `[ASSUMPTION]` / `[TBD-*]` 标注。
>
> **2026-11 存储重设计**：存储层由单 SQLite 演进为 **SQLite（唯一事实源）+ Kùzu 0.11.3（血缘图遍历层）** 双嵌入式库；全部 REST 契约不变，前端无感。方案动机、Kùzu 图模型、双写一致性、归档风险对策见 §4.3–4.5 与 §十（决策 #7/#8）。
>
> **2026-11 系统级血缘扩展（设计已定稿，代码待实现）**：在数据集/字段之上增加可选的「系统」层，用于展示**系统间上下游关系**。系统归属与系统边属性存 SQLite，系统级链路遍历走 Kùzu；系统边既可由数据集级血缘自动投影（derived），也可显式登记（explicit），两者合并为同一张关系视图，不引入新的存储栈或渲染协议。详见 §4.7、§5.3、§6.2 与 §十（决策 #9/#10）。

---

## 一、两大开源方案调研结论

### 1.1 OpenMetadata 核心设计

| 维度 | 设计 | 关键证据 |
|---|---|---|
| 数据模型 | 实体无关的「实体 + 边」图：一切资产是 Entity，血缘边挂 `LineageDetails` JSON（含列级映射 `fromColumns[] -> toColumn + function`、SQL 原文、来源枚举） | `openmetadata-spec/src/main/resources/json/schema/type/entityLineage.json` |
| 边存储 | `entity_relationship` 表（fromId/toId/fromEntity/toEntity/relation），`LineageDetails` 整体存 JSON 列；ES 里另存「反向血缘」文档做搜索 | `bootstrap/sql/migrations/.../v001__create_db_connection_info.sql` |
| 采集 | push 为主：Python ingestion（SQL 解析器、dbt、Airflow 等 18+ 连接器）+ REST API + OpenLineage。**血缘只能 CSV 导出、不能 CSV 导入** | `ingestion/src/metadata/ingestion/lineage/`、`LineageResource.java:632` |
| 查询 | DB 递归展开（depth≤3）+ ES BFS（大图按 Small/Medium/Large/Streaming 四策略）双路径 | `LineageRepository.java`、`AbstractLineageGraphBuilder.java` |
| 版本 | 实体 `Major.Minor` 版本 + change_event 表；**血缘边独立发 `ENTITY_LINEAGE_ADDED/UPDATED/DELETED` change event**，边 ID 由 fromId+toId 确定性哈希生成 | `type/changeEventType.json:45`、`LineageRepository.java:2082` |
| 前端 | **reactflow**；列级连线用 sourceHandle/targetHandle，`tracedColumns` 高亮；新 scene/hydrate 架构按 LAYER/ASSET/FIELD 分层、批量取实体消灭 N+1 | `openmetadata-ui/.../Lineage/Lineage.tsx`、`EntityLineageCanvas.tsx` |
| AI | 官方 MCP server（21 个读写工具，含 `get_entity_lineage`、`root_cause_analysis`、`create_lineage`），输出刻意 verbose（全 SQL + 列级映射）给 AI 消费 | `openmetadata-mcp/src/main/java/org/openmetadata/mcp/tools/` |
| 部署 | MySQL + Elasticsearch + Java 后端 + ingestion 容器四件套起，定位企业级平台 | `docker/docker-compose-quickstart/` |

### 1.2 DataHub 核心设计

| 维度 | 设计 | 关键证据 |
|---|---|---|
| 数据模型 | 血缘是实体上的一个 Aspect（`UpstreamLineage`），PDL 注解 `@Relationship(isLineage=true)` 声明边，系统自动物化到 ES 图索引 `graph_service_v1`；字段级用 `FineGrainedLineage`：**多对多 + transformOperation + confidenceScore(0~1)**；schemaField 是一等实体 | `metadata-models/.../dataset/UpstreamLineage.pdl`、`FineGrainedLineage.pdl` |
| 存储链路 | MCP 事件 → Kafka/REST → GMS → MySQL `metadata_aspect_v2`（urn+aspect+version+JSON）→ MCL → MAE 消费者写 ES 图/搜索索引 | `metadata-io/.../EbeanAspectDao.java:81` |
| 版本 | 三层：MCP 写前提案（含 CAS version）→ MCL 写后日志（previous/next 值）→ aspect 行级历史（latest 恒为 version=0，历史递增）；支持**按 ingestion run 回滚**；边带 createdOn 支持 PIT 时间回看 | `metadata-models/.../mxe/`、`EbeanAspectDao.java:643`、`TimelineServiceImpl.java` |
| 采集 | YAML recipe（source→transformer→sink）框架；SQL 血缘基于 sqlglot；**JSON 文件可导（file source/sink 往返），CSV 只能补描述/tag，不能导血缘** | `metadata-ingestion/src/datahub/ingestion/source/file.py`、`csv_enricher.py` |
| 查询 | GraphQL → GraphService → ES 图索引逐 hop BFS（分片、预算、超时截断）+ `searchAcrossLineage` 把过滤翻译成 ES 查询 | `ESGraphQueryDAO.java:56`、`GraphQueryPITDAO.java` |
| 前端 | 同样 **reactflow**（lineageV3）：`ColumnLineageControl` 列级连线、`LineageExplorer` 折叠展开、`manualLineage/` 手工编辑 | `datahub-web-react/src/app/lineageV3/` |
| AI | `datahub-agent-context` PyPI 包：把搜索/取详情/**trace lineage**/变更封装成 MCP + LangChain 工具给 AI agent | `datahub-agent-context/README.md` |
| 部署 | Kafka + MySQL + OpenSearch + GMS/前端等 7 个服务；有 datahub-lite 单文件嵌入式轻量变体 | `docker/quickstart/docker-compose.quickstart-profile.yml` |

### 1.3 对本方案的启示

**借鉴**：
1. 实体+边 + 边上挂详情（列级映射、转换函数、来源枚举）的 schema —— OpenMetadata 的 `entityLineage.json` 结构可直接裁剪复用；
2. `FineGrainedLineage` 的 `confidenceScore` —— AI 推断出的血缘必须带置信度、人工确认后提升，这是「AI 优化」的正确形态；
3. 每条边记录来源（Manual/Imported/AIInferred）+ 边级 change event + 确定性边 ID —— 廉价的版本管理方案；
4. reactflow 的 sourceHandle/targetHandle 列级连线 —— 两个方案都验证了这条路可行；
5. MCP/工具化接口（verbose lineage 输出 + 列级 scope 裁剪）—— AI 对话消费血缘的正确接口形态。

**避免**：
1. Kafka + ES/OpenSearch 双写与反规范化 —— 仍坚持无消息队列、无搜索集群、无服务化中间件；但把 DataHub「MySQL + ES 图索引」的形态缩小为「SQLite + 嵌入式图库 Kùzu」：SQLite 做唯一事实源，血缘拓扑以**可随时重建的派生索引**形态放 Kùzu（见 4.3–4.5），既拿到原生变长路径查询能力，又不引入任何运维组件；
2. PDL/AVRO/JSON Schema 的编译期 codegen 链与多模块工程 —— 用 pydantic 模型即可；
3. 硬编码 depth≤3 递归 + 逐节点 N+1 查询 —— 一步到位「图引擎批量变长遍历（Kùzu Cypher 主 + CTE 降级）+ 单次 hydrate」，前端一次拿全子图；
4. CSV 不能导入血缘的缺口 —— 本方案把「文件一等公民导入」作为核心功能。

---

## 二、目标与范围

**目标**：单人/小团队可独立运维的字段级数据血缘工具：
- 用户把自己整理（非第一手）的 CSV / XLSX / JSON 数据导入；
- 每个字段携带原文件精确定位（文件路径 + 工作表/行/列 / JSONPath），供他人回源核查；
- 关系型数据库存储，带版本管理；
- 可视化血缘图（节点/字段折叠、字段级连线）；
- **系统级上下游视图**：把数据集归属到业务系统后，可在同一画布上查看系统间上下游；系统边可来自数据集级血缘的自动投影，也可显式登记，并可下钻到数据集/字段证据；
- AI 对话查血缘、动态出图；
- 基于第一手资料人工纠错、补充说明。

**非目标**（从两大方案的重量级能力中明确裁剪）：
- 不做 SQL 解析自动采集、不做调度器/连接器生态；
- 不接 Elasticsearch/OpenSearch 等服务化组件；搜索用 SQLite FTS5 / LIKE，图遍历用嵌入式 Kùzu（见 4.3–4.5）；
- 不做细粒度对象级 ACL，多用户采用「工作区级 RBAC（admin / editor / viewer）+ 全操作留痕」模型（见 4.6）。若未来需要数据集级私有/授权，再引入 `dataset_acl` 表扩展。

**技术栈**（遵循个人默认偏好）：
- 后端：Python + FastAPI + uv；存储为**双嵌入式库**——SQLite（元数据/字段/版本/搜索的唯一事实源，预留 Postgres 升级路径，SQL 写兼容子集）+ Kùzu 0.11.3（血缘图专用遍历层，进程内 Cypher，无服务进程）；
- 图库采用 Kùzu **归档终版 0.11.3**（2025-10 仓库归档只读，MIT，PyPI wheel 覆盖 cp38–cp314 含 macOS arm64）：功能冻结但可用性不受影响；其角色是「可整体移除的派生层」——随时可从 SQLite 全量重建、也可退回纯 SQLite 递归 CTE 路径（风险对策见 4.5）；
- 前端：React + TypeScript + Vite + Tailwind + shadcn/ui，图渲染 **@xyflow/react（reactflow 11+）**；
- AI：OpenAI 兼容 Chat API + function calling（工具即本系统 REST API 的薄封装）；供应商与模型经仓库根 `.env` 配置（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`），`.env.example` 入库、`.env` 加入 .gitignore，密钥永不入库；
- 认证：JWT（账号密码登录），密码只存加盐哈希。

---

## 三、导入数据格式规范（需求 1）

设计为**两类文件**：`数据集清单`（描述节点和字段）与 `血缘关系`（描述边）。同一批导入绑定一次提交。用户数据基本是二手转换数据，因此格式规范的核心是：**每个字段必须携带「源文件定位器」**。

### 3.1 数据集清单（datasets & fields）

每行描述一个数据集中的一个字段：

| 列 | 必填 | 说明 |
|---|---|---|
| `dataset_id` | 是 | 数据集唯一标识（用户自定义字符串，如 `dwd_order`） |
| `dataset_name` | 否 | 显示名 |
| `field_name` | 是 | 字段名（数据集内唯一） |
| `field_type` | 否 | 类型描述（自由文本） |
| `src_file` | **是** | 引用的**已托管源文件**标识（见 3.6）：源文件库 ID 或原始文件名（须能在本批导入绑定的上传文件集中唯一定位） |
| `src_type` | **是** | `csv` / `xlsx` / `json`，决定定位器结构 |
| `src_locator` | **是** | 源文件内定位（结构见 3.2） |
| `description` | 否 | 字段说明 |
| `system_id` | 否 | 所属系统标识（见 3.7）；缺省表示未归属系统。引用必须存在于本批 `systems` 清单或已有 `system` 表 |

### 3.2 源文件定位器 `src_locator`（按 `src_type` 校验）

```jsonc
// src_type = csv：字段=原始CSV的某一列
{ "column": 3 }                    // 列序号（1-based）
{ "header": "order_no" }           // 或表头名（二选一，导入时校验）

// src_type = xlsx：字段=某工作表某列，可带数据行范围
{ "sheet": "订单明细", "column": "D", "row_start": 2, "row_end": 15000 }

// src_type = xlsx + 多级表头（Multi-header）：
// header_path 按层级匹配表头行，合并单元格的父表头自动展开覆盖其所有列
{ "sheet": "订单", "header_path": ["商品信息", "订单号"], "header_rows": 2, "row_start": 3 }

// src_type = json：字段=JSON文档某路径
{ "json_path": "$.data.items[*].order_no" }
```

> 设计理由：OpenMetadata 的 FQN 体系没有 `file:line` 级定位，这是本方案的差异化核心。定位器存 JSON 列，但导入时**按 src_type 做结构校验**，校验失败整行拒绝并给出可读错误报告（文件名、行号、原因）。

**XLSX 合并单元格 / 复杂表头归一化规则**（定位解析时统一执行）：

1. **锚点归一**：任何落在合并区域内的单元格，定位一律归一到该区域的**左上角锚点**；存储时同时记录锚点地址与合并范围（`anchor: "D2", merged_range: "D2:G8"`），保证「用户看到的合并单元格」与「存储的定位」一一对应；
2. **多级表头展开**：`header_path` 按层级逐行匹配；若某层表头是合并单元格，视为其覆盖的所有列均属于该父级（如第 1 行「商品信息」合并覆盖 B:F 列，则 `["商品信息","订单号"]` 会在 B:F 范围内继续匹配第 2 行的「订单号」）；
3. **解析结果物化**：导入时用 openpyxl 解析真实文件，把 `header_path` 解析物化为确定的 `column + row_start`，连同锚点信息一起存入 `src_locator`——后续即使源文件表头被改动，历史定位仍可回看（同时校验环节会报「定位已失效」）。

### 3.3 血缘关系（lineage）

每行描述一条字段级血缘边（数据集级边由字段级边自动推导，也允许只填表级）：

| 列 | 必填 | 说明 |
|---|---|---|
| `from_dataset` / `from_field` | 是 | 上游；`from_field` 为空表示表级血缘 |
| `to_dataset` / `to_field` | 是 | 下游 |
| `transform` | 否 | 转换说明（SQL 片段/公式/文字描述），借鉴 OpenMetadata 的 `function` + `sqlQuery` |
| `confidence` | 否 | 0~1 置信度，借鉴 DataHub `FineGrainedLineage.confidenceScore`；默认 1.0 |
| `note` | 否 | 备注 |

### 3.4 三种物理格式的承载方式

| 格式 | 承载 |
|---|---|
| CSV | 两个文件：`datasets.csv` + `lineage.csv`，UTF-8 |
| XLSX | 一个工作簿两个 sheet：`datasets` / `lineage`（单元格可加批注，适合业务人员） |
| JSON | 单文件：`{ "datasets": [...], "lineage": [...] }`，字段与上表一一对应，`src_locator` 为嵌套对象 |

导入器统一归一化为同一 pydantic 模型（`DatasetFieldRecord` / `LineageEdgeRecord`），后续处理与格式无关。

### 3.5 导入校验规则

1. 结构校验：必填列缺失、`src_type` 与 `src_locator` 结构不匹配 → 拒绝；
2. **实文件核查**（源文件已托管，见 3.6）：导入时直接打开第一手文件做机械核查——sheet 是否存在、`header_path`/`column` 能否解析、合并单元格归一化、`json_path` 能否取到值。核查不通过的行进入报告并拒绝；这一步把「用户手填定位是否正确」从人工核查变成系统自动核查；
3. 引用校验：lineage 引用的 dataset/field 必须存在于本批或已有版本；
4. 重复冲突：同 `from→to` 字段对重复时合并（后到覆盖 transform/note），并在报告中列出；
5. 产出**导入报告**（成功/跳过/失败逐条 + 失败原因 + 实文件核查结果），借鉴 ingestion report 模式，报告本身可下载为 JSON。

### 3.6 源文件托管上传

源文件（第一手资料）由系统托管，不再只存路径引用：

- **上传 API**：`POST /files`（multipart，支持批量），记录原始文件名、大小、上传者；
- **文件库表**：`source_file`（见 4.1），按 **sha256 去重**——同一文件多次上传引用同一条记录（血缘场景常出现多个字段来自同一源文件）；
- **存储后端**：默认本地 `data/files/`（目录经 `.env` 配置），存储路径不直接暴露，经 `GET /files/{id}/download` / `/preview` 权限受控访问；后端抽象成接口，预留 S3/MinIO 兼容实现 `[TBD-INFRA]`（由部署环境决定，M1 先做本地）；
- **导入流程**变为三步：① 上传源文件（得到文件集）→ ② 上传清单（datasets/lineage，`src_file` 引用文件集中文件）→ ③ 校验 + 入库（绑定到同一 `import_batch`）；
- **回源核查闭环**：定位卡点击后可直接在系统内**预览源文件对应区域**（高亮 sheet / 表头路径 / 列与行范围 / JSONPath 命中值），无需再去找原始文件。

### 3.7 系统清单与系统级血缘（可选扩展）

系统层是**可选**的：不提供系统清单时，系统级视图为空，数据集/字段级功能完全不受影响。提供时，系统清单与系统级血缘随同一 `import_batch` 入库，参与版本与回滚。

**系统清单（systems）**：

| 列 | 必填 | 说明 |
|---|---|---|
| `system_id` | 是 | 系统唯一标识（用户自定义，如 `crm` / `dw_platform`） |
| `system_name` | 否 | 显示名 |
| `system_type` | 否 | `source`（业务源系统）/ `application`（业务应用）/ `warehouse`（数仓/湖）/ `bi`（分析报表）/ `external`（外部/第三方）/ `other`；缺省 `other` |
| `owner` | 否 | 业务负责人（自由文本，不参与权限判定） |
| `description` | 否 | 系统说明 |

**系统级血缘（system_lineage）**：

| 列 | 必填 | 说明 |
|---|---|---|
| `from_system` / `to_system` | 是 | 上游/下游系统标识；必须存在于本批 `systems` 或已有 `system` 表；禁止自环 |
| `transform` | 否 | 系统间接口/加工方式说明（如「T+1 批量文件」「Kafka 实时同步」） |
| `confidence` | 否 | 0~1，默认 1.0；AI 建议边 < 1.0 |
| `note` | 否 | 备注 |

**三种物理格式**：

- CSV：在 `datasets.csv` / `lineage.csv` 之外，可选 `systems.csv` + `system_lineage.csv`；
- XLSX：可选 `systems` / `system_lineage` 两个 sheet；
- JSON：`{ "systems": [...], "datasets": [...], "lineage": [...], "system_lineage": [...] }`。

**与自动投影的关系**：`system_lineage` 只登记**无法从数据集级血缘推导**的粗粒度关系（例如「财务系统 → 数据仓库：月度对账 Excel」）。能从数据集边推导的系统关系不需要手写；查询时由 `v_system_edge` 把「显式边 ∪ 投影边」合并为同一张关系视图（见 4.7）。同一对系统既有显式边又有投影边时，显式边的 `transform/confidence/source/note` 优先，投影边的数据集边数量作为证据一并返回。

**校验规则**：

1. 系统标识唯一；`system_type` 枚举合法；
2. 数据集行的 `system_id` 引用必须存在（本批或已有版本），否则该行拒绝并给出原因；
3. 系统级血缘的上下游必须存在、禁止 `from_system = to_system`；同一对系统重复时后到覆盖 `transform/confidence/note` 并计入报告 `merged`；
4. 系统级血缘不要求存在数据集级证据——它本身就是「粗粒度关系实例」；
5. 导入报告新增 `kind=system|system_edge` 条目，沿用 3.5 的逐条 ok/merged/rejected 结构。

---

## 四、存储与版本管理（需求 2）：SQLite 事实源 + Kùzu 血缘图

### 4.1 表结构（SQLite/Postgres 通用）

```sql
-- 用户（多用户 RBAC）
user(id INTEGER PK AUTOINCREMENT,
     username TEXT UNIQUE NOT NULL,
     password_hash TEXT NOT NULL,          -- 加盐哈希，永不明文
     display_name TEXT,
     role TEXT NOT NULL CHECK(role IN ('admin','editor','viewer')),
     created_at)

-- 源文件托管（第一手资料文件库）
source_file(id INTEGER PK AUTOINCREMENT,
            original_name TEXT NOT NULL,
            storage_path TEXT NOT NULL,     -- 实际存储路径，不对外暴露
            sha256 TEXT UNIQUE NOT NULL,   -- 去重键：同文件只存一份
            size_bytes INTEGER,
            src_type TEXT NOT NULL CHECK(src_type IN ('csv','xlsx','json')),
            uploaded_by TEXT NOT NULL,
            created_at)

-- 数据集（节点）
dataset(id TEXT PK,            -- 即 dataset_id
        name TEXT, description TEXT,
        created_at, updated_at)

-- 字段（含源文件定位器）
field(id INTEGER PK AUTOINCREMENT,
      dataset_id TEXT NOT NULL REFERENCES dataset(id),
      name TEXT NOT NULL,
      field_type TEXT,
      source_file_id INTEGER NOT NULL REFERENCES source_file(id),
      src_locator TEXT NOT NULL,      -- JSON：定位器 + 实文件解析物化结果（锚点/合并范围/行列）
      description TEXT,
      UNIQUE(dataset_id, name))

-- 血缘边（表级 + 字段级统一存一张表；表级边 field 为 NULL）
edge(id INTEGER PK AUTOINCREMENT,
     from_dataset TEXT NOT NULL, from_field TEXT NULL,
     to_dataset   TEXT NOT NULL, to_field   TEXT NULL,
     transform TEXT, confidence REAL DEFAULT 1.0,
     source TEXT NOT NULL CHECK(source IN ('imported','manual','ai')),
     note TEXT,
     created_by TEXT, updated_by TEXT,
     created_at, updated_at,
     UNIQUE(from_dataset, from_field, to_dataset, to_field))
-- 确定性语义：同一 from→to 只有一条边（等价 OpenMetadata 的 (fromId,toId,relation) 主键）

-- 导入批次 = 版本（借鉴 DataHub 的 ingestion run）
import_batch(id INTEGER PK, version_no INTEGER NOT NULL UNIQUE,  -- v1, v2, ...
             file_names TEXT, format TEXT, report TEXT,  -- 导入报告 JSON
             created_by TEXT NOT NULL,
             created_at)

-- 版本业务标签（发布版本号，如 v2.1-r1）
version_tag(id INTEGER PK,
            name TEXT UNIQUE NOT NULL,       -- 业务标签名
            note TEXT,                       -- 标签说明（如「Q3 口径修正发布」）
            batch_id INTEGER,                 -- 打标签时对应的导入批次
            change_seq INTEGER NOT NULL,      -- change_log 中的位置（时间点锚）
            created_by TEXT NOT NULL, created_at)

-- 字段级/边级覆盖层：编辑说明与人工修正
annotation(id INTEGER PK, target_kind TEXT CHECK(target_kind IN ('field','edge','dataset')),
           target_id TEXT,          -- field:"ds.field" / edge:"from->to" / dataset:id
           body TEXT NOT NULL, author TEXT, created_at)

-- 变更日志（借鉴 OpenMetadata ENTITY_LINEAGE_* change event + DataHub MCL）
change_log(id INTEGER PK, batch_id INTEGER NULL,  -- 关联导入批次；人工编辑为 NULL
           entity_kind TEXT, entity_key TEXT,
           op TEXT CHECK(op IN ('added','updated','deleted')),
           before TEXT, after TEXT,   -- JSON 快照
           actor TEXT, created_at)
```

> 2026-11 系统级血缘新增 `system` / `system_edge` 两张表，并给 `dataset` 增加可空 `system_id`；完整 DDL 见 4.7.1，逐列定义见《数据模型》§2.13/§2.14。它们与现有表同属 SQLite 事实源，不改变「单进程 + 双嵌入式库」的部署形态。

### 4.2 版本管理设计
采用 **「当前态 + 导入批次 + 版本标签 + 变更日志」** 四层，而非全量快照（数据量小到中等时最省、可回滚）：

1. **导入即新版本**：每次导入创建 `import_batch`，`version_no` 递增（v1, v2...）；
2. **写前提案/写后日志**（DataHub 思路的轻量化）：导入或编辑的每一行变更都写 `change_log`（op + before/after JSON），批次和日志天然支持「**按版本回滚**」——把该批次产生的 added 反向删除、updated 恢复 before；
3. **版本业务标签**：任意时刻可打标签（如 `v2.1-r1 / Q3 口径修正发布`），标签锚定一个 `change_seq` 位置。**回滚到标签 = 反做该 seq 之后的全部 change_log**，**标签间 diff = change_log 区间比对**；标签由 editor 以上角色创建，永久保留；
4. **编辑来源可追溯**：边上的 `source` 字段区分 `imported`（用户文件来的）/ `manual`（人工纠正）/ `ai`（AI 推断，confidence < 1），配合 `created_by` 落到具体用户。

### 4.3 Kùzu 血缘图（拓扑派生层，2026-11 新增）

**职责边界（一条铁律）**：SQLite 是唯一事实源（元数据、字段、边、版本、审计全部在 SQLite）；Kùzu 只存**血缘拓扑 + 少量过滤列**，是「随时可以从 SQLite 全量重建的图索引」。它对应 DataHub 架构里 ES `graph_service_v1` 图索引的位置，只是从服务化搜索引擎缩小成了进程内嵌入式图库。

**选型要点**：

- Kùzu 是嵌入式属性图数据库（「图数据库界的 SQLite/ DuckDB」形态）：无服务进程、无端口、随 Python 进程启动，`pip install kuzu` 即用；
- 原生 Cypher 支持**变长路径**（`*1..n`）与路径函数，这正是血缘遍历的核心算子——SQLite 递归 CTE 也能做，但变长跳数控制、路径去重、按跳过滤都要手写展开；
- 0.11.3 归档终版内置 `algo` 扩展（环路检测、PageRank 等），为「影响面排序」类 AI 工具预留了原生算法入口；
- 归档风险接受（见 §十 决策 #8）：MIT + 源码完整 + wheel 全平台可用，功能冻结对血缘图这类稳定负载无影响；且 Kùzu 数据**永远可以从 SQLite 推导**，最坏情况整体移除即回到 CTE 单库方案，无数据丢失风险。

**图模型 DDL**（节点只存身份键与展示名，完整元数据一律回 SQLite 取）：

```cypher
CREATE NODE TABLE Dataset (id STRING, name STRING, PRIMARY KEY (id));
CREATE NODE TABLE Field   (id STRING, name STRING, PRIMARY KEY (id));  -- id = "<dataset_id>.<field_name>"，与 §5.2 自然键一致

CREATE REL TABLE LINEAGE_FIELD (FROM Field TO Field,
    edge_id INT64,          -- SQLite edge.id：回链主库的稳定键（编辑/删除/转正都按它定位）
    source STRING,          -- imported / manual / ai（画布过滤需要）
    confidence DOUBLE);     -- 置信度（低置信过滤需要）
CREATE REL TABLE LINEAGE_TABLE (FROM Dataset TO Dataset,
    edge_id INT64, source STRING, confidence DOUBLE);
```

> Kùzu 关系表端点固定，故字段级/表级血缘拆成两张 REL 表（与 SQLite `edge` 单表 NULL 字段语义等价，映射规则见《数据模型》§十）。transform/note/annotation 等业务属性**不进图**——查询先走图取拓扑与 edge_id，再回 SQLite hydrate，双写漂移面被压到最小。

### 4.4 图遍历：Kùzu Cypher 主路径 + 递归 CTE 降级

两大方案的教训：OpenMetadata 初版 depth≤3 硬编码 + N+1 查询；DataHub 用 ES 图索引 + 分片预算。本方案的查询路由：

| 查询 | 引擎 | 说明 |
|---|---|---|
| 元数据/搜索/详情/历史 | **SQLite** | 字段详情、annotation、change_log、FTS5/LIKE 搜索，永远走主库 |
| 血缘拓扑（trace/subgraph/impact） | **Kùzu（主）** | Cypher 变长路径一次取出 N 跳子图；命中 edge_id 后回 SQLite hydrate |
| 血缘拓扑（降级） | SQLite 递归 CTE | Kùzu 不可用/图状态为 dirty 且重建失败时自动切换（同一 REST 契约） |

核心查询形态（`trace_lineage` / `get_subgraph` / `analyze_impact` 共用）：

```cypher
-- 1-hop 上游（字段详情面板）
MATCH (src:Field)-[r:LINEAGE_FIELD]->(f:Field {id: $fid})
RETURN src.id, r.edge_id, r.confidence ORDER BY r.confidence DESC;

-- N-hop 上游全链（变长路径，跳数上限由服务端白名单注入）
MATCH p = (src:Field)<-[:LINEAGE_FIELD*1..3]-(f:Field {id: $fid})
RETURN src.id, r.edge_id, length(p) AS hop ORDER BY hop;

-- 下游影响面（analyze_impact 工具）
MATCH p = (f:Field {id: $fid})-[:LINEAGE_FIELD*1..5]->(down:Field)
RETURN down.id, length(p) AS hop;
```

查询结果仍组装为同一 `GraphPayload`（nodes + edges + 字段）返回，**REST 契约与前端渲染协议完全不变**——换引擎对前端透明。递归 CTE 实现保留在 `lineage.py` 作为降级路径，不删除。

### 4.5 双写与一致性：SQLite 唯一事实源

所有写路径（导入、画布编辑、AI 建议确认/拒绝、回滚）按「**先主库、后图库、失败标脏**」顺序双写：

```
写请求 → ① SQLite 事务（edge + change_log 等）
       → 成功后 → ② Kùzu 事务（CREATE/DELETE 对应 Rel）
                    ├─ 成功 → 响应 200（正常）
                    └─ 失败 → graph_state.state = 'dirty' → 仍响应 200（派生层失败不阻断业务写）
血缘读请求 → graph_state 为 clean → 走 Kùzu
            → 为 dirty → 自动触发全量重建（秒级）→ 成功则继续；失败则降级 CTE
```

- **为什么先主库**：写操作的真实性由 SQLite + change_log 承诺；Kùzu 挂了只损失图查询性能，不损失任何业务数据——这是把 Kùzu 定义为「派生层」而非「联合事实源」的直接收益；
- **全量重建替代增量同步**：本方案数据规模小（万级边以内），重建 = 从 SQLite `edge` 全量导出 → 清空 REL 表 → Kùzu `COPY FROM` 批量导入，秒级完成且**幂等、无漂移累积**；刻意不做逐条增量同步（同步逻辑本身是漂移源头）。未来数据量增长再引入 change_log 水位增量优化 `[TBD-BE]`；
- **状态与审计**：`graph_state` 单行表（SQLite）记录 `last_edge_id` 水位、`state('clean'|'dirty')`、`rebuilt_at`；`/health` 与画布顶栏展示图状态徽标（正常 / 重建中 / 降级 CTE），重建动作写 `change_log`（`entity_kind='graph'`）留痕；
- **漂移审计**：提供 `clew graph audit` 命令：比对 Kùzu 边集与 SQLite 边集（按 edge_id 集合差），不一致即标脏重建；后台任务每次导入完成后跑一次。

### 4.6 用户与权限（多用户）

JWT 认证 + 工作区级 RBAC 三角色，所有写操作（导入、编辑、标注、打标签）在 change_log / 各表 `created_by` 中记录操作者：

| 角色 | 权限 |
|---|---|
| `viewer` | 浏览血缘图、查看字段详情与源文件预览、AI 只读问答（trace/search/get_subgraph） |
| `editor` | viewer + 上传源文件、导入清单、画布编辑（纠错/连线/改定位器）、标注、创建版本标签、确认 AI 建议边 |
| `admin` | editor + 用户与角色管理、按批次/标签回滚、删除数据集、重置导入 |

实现为 FastAPI 依赖注入的角色守卫（每个路由声明最低角色），不做行级/对象级 ACL；`annotation` 与 `change_log` 中的 author/actor 均取自 JWT，不可伪造。

### 4.7 系统级血缘：同一分层架构上的「第三层视图」（2026-11 新增设计）

**现状判定（2026-11-16）**：当前数据模型只有 `dataset` / `field` / `edge`，没有系统实体、数据集归属与系统边；API 与画布也只提供数据集/字段级视图。因此**当前系统不支持开箱即用的系统间上下游展示**。若用「把系统建成数据集、用表级边模拟」的方式绕过，会丢失系统目录（类型/负责人）、数据集归属、系统边来源与证据计数、系统级 N 跳遍历等语义，不建议作为正式方案。

**定位**：系统级上下游不是另起炉灶，而是把已有的「实体属性与入口检索 → 关系库；关系实例与链路遍历 → 图数据库」分层原样上移一层：

| 层 | 实体属性 / 入口检索（SQLite） | 关系实例 / 链路遍历（Kùzu） | 渲染协议 |
|---|---|---|---|
| 系统级 | `system` 目录、`dataset.system_id` 归属、系统搜索 | `System` 节点 + `LINEAGE_SYSTEM` 关系，N 跳系统链路 | `SystemGraphPayload` |
| 数据集级 | `dataset` 元数据、`v_dataset_edge` 投影 | `Dataset` 节点 + `LINEAGE_TABLE` 关系 | `GraphPayload` |
| 字段级 | `field` 元数据、定位器、标注、历史 | `Field` 节点 + `LINEAGE_FIELD` 关系 | `GraphPayload` |

三层共用同一个 FastAPI 进程、同一个 SQLite 事实源、同一个 Kùzu 派生图与同一套画布交互；**没有新增服务、消息队列或搜索集群**。系统视图只是把 `GraphPayload` 的节点类型从 dataset/field 换成 system，前端按 `level` 选择渲染器。

**4.7.1 表结构**

```sql
-- 系统目录（实体属性 + 入口检索在 SQLite）
system(id TEXT PRIMARY KEY,        -- 用户自定义标识，如 crm / dw_platform
       name TEXT, description TEXT,
       system_type TEXT NOT NULL DEFAULT 'other'
         CHECK(system_type IN ('source','application','warehouse','bi','external','other')),
       owner TEXT,                 -- 业务负责人，自由文本
       created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

-- 数据集归属（可选；NULL = 未归属系统）
ALTER TABLE dataset ADD COLUMN system_id TEXT REFERENCES system(id) ON DELETE SET NULL;

-- 显式系统级血缘（只登记无法从数据集边推导的粗粒度关系）
system_edge(id INTEGER PK AUTOINCREMENT,
            from_system TEXT NOT NULL REFERENCES system(id),
            to_system   TEXT NOT NULL REFERENCES system(id),
            transform TEXT, confidence REAL DEFAULT 1.0 CHECK(0 <= confidence <= 1),
            source TEXT NOT NULL CHECK(source IN ('imported','manual','ai')),
            note TEXT,
            created_by TEXT, updated_by TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            CHECK(from_system <> to_system));
CREATE UNIQUE INDEX uq_system_edge ON system_edge(from_system, to_system);
```

**4.7.2 关系视图：显式边 ∪ 投影边**

系统级关系有两个来源，查询时合并，**不双写**：

1. **explicit（显式）**：`system_edge` 中登记的系统间关系，可携带接口说明/置信度/来源；不要求存在数据集级证据；
2. **derived（投影）**：把 `edge` 两端的 dataset 通过 `dataset.system_id` 映射到系统，`COUNT(DISTINCT 数据集对)` 聚合成一条系统边；同一系统内部的数据集边不产生系统边（排除自环）；
3. **both（两者都有）**：同一对系统既有显式边又有投影边；显式边的业务属性优先，投影边只提供 `dataset_edge_count` 证据计数。

```sql
CREATE VIEW v_system_edge AS
WITH derived AS (
  SELECT d_from.system_id AS from_system,
         d_to.system_id   AS to_system,
         COUNT(DISTINCT e.from_dataset || '->' || e.to_dataset) AS dataset_edge_count,
         MIN(e.confidence) AS confidence
  FROM edge e
  JOIN dataset d_from ON d_from.id = e.from_dataset
  JOIN dataset d_to   ON d_to.id   = e.to_dataset
  WHERE d_from.system_id IS NOT NULL
    AND d_to.system_id IS NOT NULL
    AND d_from.system_id <> d_to.system_id
  GROUP BY d_from.system_id, d_to.system_id
),
explicit AS (
  SELECT id, from_system, to_system, transform, confidence, source, note
  FROM system_edge
)
SELECT e.from_system, e.to_system,
       CASE WHEN d.from_system IS NOT NULL THEN 'both' ELSE 'explicit' END AS origin,
       COALESCE(d.dataset_edge_count, 0) AS dataset_edge_count,
       e.id AS system_edge_id,
       e.transform, e.confidence, e.source, e.note
FROM explicit e
LEFT JOIN derived d ON d.from_system = e.from_system AND d.to_system = e.to_system
UNION ALL
SELECT d.from_system, d.to_system, 'derived', d.dataset_edge_count,
       NULL, NULL, d.confidence, 'derived', NULL
FROM derived d
LEFT JOIN explicit e ON e.from_system = d.from_system AND e.to_system = d.to_system
WHERE e.id IS NULL;
```

> 设计取舍：投影边**不落库**，避免「数据集边改了、系统边忘了改」的双写漂移；系统级边数在万级以下，视图 + 图重建的成本可忽略。显式边落库是因为它承载了投影无法表达的业务信息（接口方式、责任人、无数据集明细的粗粒度关系），并且必须参与版本与回滚。

**4.7.3 Kùzu 图模型**

```cypher
CREATE NODE TABLE System (id STRING, name STRING, system_type STRING, PRIMARY KEY (id));
-- Dataset 节点新增 system_id 属性（空串表示未归属），用于系统下钻与归属过滤
CREATE NODE TABLE Dataset (id STRING, name STRING, system_id STRING, PRIMARY KEY (id));

CREATE REL TABLE LINEAGE_SYSTEM (FROM System TO System,
    system_edge_id INT64,        -- 显式边 = system_edge.id；纯投影边 = -1
    origin STRING,               -- explicit / derived / both
    source STRING,               -- imported / manual / ai / derived
    confidence DOUBLE,
    dataset_edge_count INT64);   -- 投影证据计数（显式边为 0）
```

- `LINEAGE_SYSTEM` 的每条关系对应 `v_system_edge` 的一行；重建时从视图全量 `COPY FROM`，与数据集/字段图同一套「SQLite 唯一事实源 + Kùzu 可重建派生层」流程（4.5）；
- 纯投影边 `system_edge_id = -1`（Kùzu 属性用哨兵值而非 NULL，便于审计与过滤）；显式边回链 `system_edge.id`，编辑/删除/转正按它定位；
- `Dataset.system_id` 是归属属性而非血缘关系：系统下钻时按它过滤数据集，不参与 `LINEAGE_*` 遍历。

**4.7.4 查询路由与环处理**

| 查询 | 引擎 | 说明 |
|---|---|---|
| 系统列表/详情/搜索 | SQLite | `system` + `dataset.system_id` 聚合；`search_systems` 用 LIKE |
| 系统 N 跳上下游 | Kùzu（主） | `MATCH p=(s:System {id:$sid})<-[:LINEAGE_SYSTEM*1..n]-(up:System)`，下游同向；`RETURN DISTINCT up.id, min(length(p)) AS hop` |
| 系统边证据 | SQLite | 按 `v_system_edge` 取 `dataset_edge_count`，再按两端系统反查 `edge` 明细（下钻面板） |
| 降级 | SQLite 递归 CTE | Kùzu 不可用/图 dirty 且重建失败时，对 `v_system_edge` 做递归闭包；同一 REST 契约 |

**环处理（必须实现）**：数据集级血缘按业务规则应无环，但**投影到系统级后可能产生环**（例如 A 系统两个数据集互相引用，或 X→Y 与 Y→X 同时存在）。因此系统级遍历必须：① 用 `DISTINCT` + `min(hop)` 去重；② 跳数上限沿用 1~5 白名单；③ `clew graph audit` 报告系统级环，UI 在环上显示提示；④ 不以系统级环反推数据集级有环。

**4.7.5 版本、回滚与一致性**

- `system` 与 `system_edge` 是**一等版本化实体**：创建/修改/删除写 `change_log`（`entity_kind='system'|'system_edge'`），参与按批次/按标签回滚；
- `dataset.system_id` 变更写 `change_log(entity_kind='dataset', op='updated')`；数据集快照新增 `system_id` 键。导入新建数据集写 `added` 快照，回滚时按「先删边、再删字段、最后删数据集」的反做顺序执行；
- 回滚完成后 `graph_state.state='dirty'`，下次系统级读请求自动全量重建 Kùzu（系统节点/关系与数据集/字段图一起重建），无需逐条反向操作；
- `graph_state` 增加 `system_rel_count`，导入完成后与 `SELECT COUNT(*) FROM v_system_edge` 做廉价对账；`clew graph audit` 再做 `system_edge_id` 集合级精确比对；
- 删除系统：`ON DELETE SET NULL` 解除数据集归属；显式 `system_edge` 随系统删除级联清理（应用层先删边再删系统，并写 `deleted` 日志）；投影边因归属清空而自然消失。

**4.7.6 不变量**

1. 系统标识唯一；`system_edge` 同一上下游对唯一；禁止自环；
2. 系统级边**不要求**有数据集级证据（显式边可以只有接口说明）；但一旦展示 `origin=derived/both`，`dataset_edge_count` 必须与底层 `edge` 投影一致；
3. 系统级环允许存在，但必须可检测、可提示、不阻断查询；
4. 未归属系统的数据集不进入系统图；UI 以「未归属 N 个数据集」计数提示，不伪造虚拟系统节点；
5. 系统级视图与数据集/字段级视图使用同一权限模型（viewer 只读、editor 可编辑、admin 可删除系统/回滚）。

---

## 五、可视化界面（需求 3）

技术选型：**@xyflow/react（reactflow）** —— 两个方案都选择它，列级连线（sourceHandle/targetHandle）、节点折叠、布局生态都被验证过，抄作业风险最低。zustand 做画布状态。

### 5.1 核心交互

| 需求 | 实现 |
|---|---|
| 展示感兴趣的数据集 | 顶部搜索/选择起点数据集 → `GET /lineage/subgraph`（Kùzu Cypher，降级 CTE）取上下游 N 跳子图 |
| 上下游关系 | 左右流向布局（dagre 自动布局），上游在左、下游在右 |
| 字段级连线 | 节点卡片内每个字段渲染为可连接的 handle 行，字段级边画 handle→handle 连线；表级边画节点→节点 |
| 折叠字段/节点 | reactflow 节点内 `collapsed` 状态：折叠节点收起字段列表（仅显示表级边）；折叠一组节点收起为一个分组占位节点（OpenMetadata `LoadMoreNode` 的思路） |
| 源文件定位 | 字段行 hover/点击弹出定位卡：源文件名 + 定位器人类可读形式（如 `订单明细.xlsx #sheet「订单明细」 D2:D15000`）。由于源文件已托管（3.6），点击定位卡可**在系统内直接预览源文件对应区域**（高亮表头路径/列/行范围/JSONPath 命中值），一键复制 |
| 过滤 | 按数据集名、字段名、置信度（隐藏 AI 低置信边）、编辑来源过滤 |

### 5.2 与 AI 出图共用同一渲染协议

后端所有「取子图」能力统一返回一种 `GraphPayload`（nodes + edges + 字段），前端只有一个渲染入口；搜索出图、点击展开、AI 对话出图都走它，避免 OpenMetadata 那样新旧两套图架构并存。

### 5.3 系统级视图与下钻（2026-11 新增）

画布顶部增加**层级切换**：`系统 / 数据集 / 字段`，三者共用同一画布骨架（缩放、平移、筛选、详情面板、边列表），只切换数据源与节点渲染器：

| 层级 | 节点 | 边 | 下钻 |
|---|---|---|---|
| 系统 | 系统卡片：名称、类型徽标（源系统/应用/数仓/BI/外部）、数据集数、负责人 | 系统间上下游；显式边实线、投影边虚线；边上标注 `数据集边数` | 双击系统 → 数据集视图（按该系统过滤）；点「证据」→ 展开底层数据集边 |
| 数据集 | 数据集卡片（可折叠字段） | 表级/字段级投影；沿用现有样式 | 双击数据集 → 字段视图；字段详情/回源预览不变 |
| 字段 | 现有字段级画布 | 字段级边 | — |

**系统视图的关键交互**：

1. **方向**：左右布局，上游在左、下游在右；工具栏提供 `both / up / down` 方向与 1~5 跳；
2. **边来源可解释**：边详情必须显示 `origin`（explicit / derived / both）、`dataset_edge_count`、底层数据集边清单（来自 SQLite），以及显式边的 `transform/note/confidence/source`；不允许只画一条无法解释来源的线；
3. **证据下钻**：选中系统边 → 右侧「关系证据」面板列出贡献该边的数据集级边（`from_dataset.field → to_dataset.field`），点击任一条跳到数据集/字段视图并高亮；
4. **未归属数据集**：侧栏显示「未归属系统 N 个数据集」，点击列出清单；系统图不生成虚拟节点；
5. **环提示**：系统级环（投影产生）在画布与边列表上标记「环」徽标，提示「系统级聚合环，不等于数据集级环」；
6. **AI 候选**：`source='ai'` 的系统边以虚线 + 低置信样式呈现，确认前不参与「已确认链路」统计；
7. **同一渲染协议**：系统图响应 `SystemGraphPayload`（§5.2 的 GraphPayload 同构：`systems[]` + `edges[]` + `seed` + `level`），AI 出图与手工浏览共用前端 `applyGraph` 入口。

> 交互原型：[clew-system-lineage-prototype.html](../02_prototype/clew-system-lineage-prototype.html)（系统/数据集/字段三级切换、显式边与投影边区分、证据下钻、未归属提示、系统级环演示）。原型只验证信息架构，不代表后端已实现。

---

## 六、AI 对话（需求 4）

### 6.1 形态

聊天面板（侧边抽屉）+ 画布联动。AI 通过 **function calling** 调用本系统 API 工具，工具返回结构化数据，AI 组织回答，同时前端把工具结果中的 `graph` 渲染到画布。

### 6.2 工具集（薄封装 REST，借鉴 OpenMetadata MCP 的 verbose 原则 + datahub-agent-context 的接口形态）

| 工具 | 对应 API | 说明 |
|---|---|---|
| `search_fields` | `GET /search?q=` | 按名字/描述/说明模糊找字段 |
| `get_field_details` | `GET /fields/{ds}.{f}` | 字段详情 + 源文件定位器 + 标注历史 |
| `trace_upstream` / `trace_downstream` | `GET /lineage/trace` | Kùzu Cypher 变长路径取上下游（降级递归 CTE），参数：起点字段、方向、最大跳数、是否含表级边 |
| `get_subgraph` | `GET /lineage/subgraph` | 取子图 `GraphPayload`，前端渲染 |
| `get_field_history` | `GET /changes?entity=` | 字段的版本变更历史 |
| `search_systems` | `GET /systems?q=` | 按系统名/标识/说明检索系统 |
| `trace_system_lineage` | `GET /lineage/systems` | 系统级 N 跳上下游（Kùzu `LINEAGE_SYSTEM`，降级 `v_system_edge` 递归 CTE）；返回系统图 |
| `get_system_details` | `GET /systems/{id}` | 系统属性 + 数据集清单 + 上下游系统 + 显式边证据 |
| `suggest_lineage` | `POST /ai/suggest` | **AI 反向优化**：AI 根据字段名/描述/相似度提议可能缺失的血缘边（confidence 低、source='ai'），用户在图上确认/拒绝 |
| `suggest_system_lineage` | `POST /ai/suggest/systems` | 系统级候选边（如「CRM → 营销平台」），source='ai'，必须人工确认才转 manual |

> 系统级工具与字段级工具遵循同一权限与安全规则：`search_systems` / `trace_system_lineage` / `get_system_details` 只读；`suggest_system_lineage` 属写类工具，工具层按调用方角色校验，viewer 触发只回传错误、不落库；AI 建议的系统边必须人工确认（editor+）后才转 `manual`（不变量#4）。

### 6.3 示例对话流

> 用户：`订单表里的 order_no 是从哪来的？`
> AI 调 `search_fields("order_no")` → `trace_upstream(ds=xxx, field=order_no, hops=3)`
> 回答：「`order_no` 由 `ods_raw.order_id` 经 `cast/trim` 得到（2 跳，置信度 1.0），源头字段位于 `订单明细.xlsx` sheet「订单明细」D 列」+ 前端画布自动切换到该字段上下游子图。

### 6.4 AI 优化的两条路径

1. **查询侧**（需求 4 主体）：自然语言 → 工具调用 → 动态出图；
2. **数据质量侧**（需求 5 的辅助）：`suggest_lineage` 用同名/语义相似/上下游邻近启发式 + LLM 判断，产出低置信候选边，**必须人工确认**才转 `source='manual'`——这是从 DataHub `confidenceScore` 借来的关键安全设计。

---

## 七、人工纠错与标注（需求 5）

| 能力 | 设计 |
|---|---|
| 编辑节点/字段 | 画布节点详情面板：改名、改描述、**修正 src_locator**（基于第一手资料核对后改定位） |
| 编辑边 | 改 transform/note、删除错误边、新增边（图上拖 handle 连线，等价 DataHub `manualLineage`） |
| 补充说明 | `annotation` 表：对任意字段/边/数据集添加说明条目（body + author + 时间），**追加式不覆盖原始导入值**——原始导入数据与人工见解分离，方便他人理解 |
| 全量留痕 | 每次编辑写 `change_log`（before/after），支持查看某字段「谁在何时改了什么」 |
| 回滚 | 按导入批次回滚（4.2）；单条编辑可通过 change_log 恢复 before |

---

## 八、总体架构

```
┌───────────────────────────────┐
│  前端 SPA (React + Vite)       │
│  ├─ 登录/用户（JWT）            │
│  ├─ 血缘画布 (@xyflow/react)   │
│  ├─ 导入向导（传源文件→传清单→报告）│
│  └─ AI 聊天抽屉（工具调用联动画布）│
└──────────────┬────────────────┘
        REST / JSON (JWT 鉴权 + RBAC 守卫，契约不变)
┌──────────────┴────────────────┐
│  FastAPI 后端（单进程）         │
│  ├─ auth：JWT + 角色守卫       │
│  ├─ importer：csv/xlsx/json   │
│  │   归一化 + pydantic 校验     │
│  │   + 实文件定位核查(openpyxl) │
│  ├─ files：源文件托管/去重/预览 │
│  ├─ lineage：图查询路由         │
│  │   Kùzu Cypher（主）          │
│  │   ├─ Field/Dataset 血缘      │
│  │   └─ System 系统级血缘       │
│  │   ↘ 递归 CTE（降级）         │
│  ├─ systems：系统目录/归属      │
│  │   显式边 + 投影视图合并       │
│  ├─ graph：双写 / 标脏 / 重建   │
│  ├─ versioning：批次/标签/日志  │
│  └─ ai：function calling 编排   │
└──────────────┬────────────────┘
   ┌──────────┴───────────┐
   ▼                      ▼
SQLite（唯一事实源）      Kùzu 0.11.3（血缘图派生层）
 user/dataset/field/     Dataset/Field 节点表
 system/system_edge/     System 节点表
 edge/import_batch/      LINEAGE_FIELD/TABLE/SYSTEM
 version_tag/annotation/ （edge_id/system_edge_id 回链主库）
 change_log/...+FTS5     │ 不可用→标脏→自动重建
 data/files/ 源文件托管   │ 重建失败→读路径降级 CTE
   （sha256 去重）
[预留 Postgres（主库升级路径）/ S3；Kùzu 可整体移除回退 CTE]
```

与两大方案最大的架构差异：**单进程、双嵌入式存储、无消息队列、无搜索集群**。DataHub 的事件驱动（Kafka+MCP+MCL）用「同步写 + change_log 表」替代；OpenMetadata/DataHub 的 ES 图索引缩小为进程内 Kùzu 图层——**查询主入口永远在 SQLite**，Kùzu 只服务血缘拓扑遍历且可随时从 SQLite 重建（4.5）。系统级血缘沿用同一分层：系统属性/归属/搜索在 SQLite，系统关系实例与 N 跳遍历在 Kùzu；系统边不是第三套存储，而是 `v_system_edge`（显式 ∪ 投影）在图层的一个投影（4.7）。

---

## 九、里程碑（建议）

| 阶段 | 内容 | 验证标准 |
|---|---|---|
| M1 数据底座 | 表结构（含 user/source_file/version_tag/graph_state）、JWT 认证 + RBAC、源文件上传与 sha256 去重、CSV/JSON/XLSX 导入器（含合并单元格/多级表头定位解析与实文件核查）、版本批次/change_log、Kùzu 图初始化与双写（导入即写图，失败标脏） | 三种格式各一份样例（含复杂表头 xlsx）导入通过；错误定位器被实文件核查拒绝；回滚 v2 → 恢复 v1 状态且 Kùzu 图同步重建；viewer 角色无法写入 |
| M2 图查询 + 画布 | Kùzu Cypher 图查询 API（trace/subgraph/impact，降级 CTE）+ `clew graph audit/rebuild` + reactflow 画布：子图渲染、字段级连线、折叠、定位卡 + 源文件区域内预览、图状态徽标 | 手工构造 5 数据集样例，上下游 3 跳展开正确（Cypher 与 CTE 两条路径结果一致）、折叠正常、点击定位卡能高亮预览源文件区域；删除 Kùzu 文件后自动重建成功 |
| M3 编辑与标注 | 画布编辑边/字段（editor 以上）、标注、历史查看、版本业务标签与标签 diff/回滚 | 编辑留痕（记录操作者）、按标签回滚正确、人工标注不丢 |
| M4 AI 对话 | 工具集 + 聊天抽屉 + 联动出图 + suggest_lineage（确认权限 editor 以上） | 「order_no 从哪来」类问题正确出图；AI 建议边需人工确认才生效 |
| M6 系统级血缘（2026-11 新增设计，代码待实现） | `system` / `system_edge` 表与迁移、`dataset.system_id` 归属、`v_system_edge`（显式 ∪ 投影）、Kùzu `System` 节点与 `LINEAGE_SYSTEM`、系统图 API + 降级 CTE、画布层级切换与证据下钻、导入清单扩展、系统级 AI 只读工具 | 同一系统内数据集边不产生自环；数据集边投影出的系统边与 `dataset_edge_count` 一致；显式边与投影边合并为 `both` 且显式属性优先；系统级 N 跳（含环）不重复节点、跳数正确；删除 Kùzu 文件后系统图自动重建；系统/系统边/归属变更可按批次与标签回滚 |

---

## 十、已确认决策记录（2026-10-23）

| # | 事项 | 决策 | 设计落点 |
|---|---|---|---|
| 1 | 多用户权限 | **需要**。采用工作区级 RBAC（admin/editor/viewer）+ JWT + 全操作留痕；不做对象级 ACL | 4.4 用户与权限 |
| 2 | 版本业务标签 | **需要**。`version_tag` 表，标签锚定 change_log 位置，支持标签间 diff 与回滚到标签 | 4.1 / 4.2 |
| 3 | 源文件托管上传 | **需要**。`source_file` 表 + sha256 去重 + 受控预览/下载；附带收益：导入时可对第一手文件做定位器实文件核查，画布定位卡支持区域内预览 | 3.5 / 3.6 |
| 4 | XLSX 复杂表头 | **需要支持**。合并单元格锚点归一化 + 多级表头 `header_path` 展开 + 解析结果物化存储 | 3.2 归一化规则 |
| 5 | LLM 供应商 | OpenAI 兼容 API，配置在仓库根 `.env`（`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`），`.env` 不入库 | 二 技术栈 |
| 6 | 界面布局 | **低保真原型已确认（2026-10-23）**，作为 UI 基线。共 6 界面：血缘画布（核心）、源文件预览（回源核查弹窗）、导入向导（三步+校验报告）、AI 对话（工具追溯+建议确认）、版本与用户（批次/标签/回滚+RBAC 矩阵）、登录 | 五 可视化界面 |

**2026-11-16 新增决策（存储重设计）**：

| # | 事项 | 决策 | 设计落点 |
|---|---|---|---|
| 7 | 存储方案 | **SQLite + Kùzu 双嵌入式库配合**：SQLite 作为查询主入口的底层数据存储层（元数据/搜索/版本/审计的唯一事实源）；Kùzu 作为血缘关系查询的专用存储层（拓扑遍历 + 少量过滤列）。REST 契约不变，前端无感 | 4.3 图模型 / 4.4 查询路由 / 4.5 双写一致性 |
| 8 | Kùzu 归档风险 | 接受使用归档终版 0.11.3（2025-10 仓库只读，MIT，cp38–cp314 wheel 全平台可用）。对策：① Kùzu 定义为可随时重建的派生层，SQLite 永远是唯一事实源；② 标脏自动重建 + `clew graph audit/rebuild`；③ 递归 CTE 路径永久保留，可整体退回单库方案，无数据丢失风险 | 4.5 / §二 技术栈 |
| 9 | 系统级上下游 | **需要**。新增可选 `system` 层：`system` 目录 + `dataset.system_id` 归属 + `system_edge` 显式边；系统图 = 显式边 ∪ 数据集边投影（`v_system_edge`），不双写。系统属性/搜索走 SQLite，系统级 N 跳走 Kùzu `LINEAGE_SYSTEM`，降级 `v_system_edge` 递归 CTE；沿用现有 GraphPayload 渲染协议 | 3.7 / 4.7 / 5.3 / 6.2 |
| 10 | 系统边来源与证据 | 系统边必须可解释：`origin=explicit/derived/both`、`dataset_edge_count`、底层数据集边清单；显式边属性优先，投影边只提供证据计数；允许系统级聚合环，但必须检测、提示、不阻断查询；未归属数据集不生成虚拟系统节点 | 4.7.2 / 4.7.4 / 5.3 |

剩余待定项（不阻塞 M1 开发）：
- `[TBD-INFRA]` 源文件存储后端 M1 用本地 `data/files/`，S3/MinIO 抽象接口何时实做，由部署环境决定；
- `[TBD-BIZ]` 是否需要数据集级私有/授权（当前工作区内所有用户可见所有数据集），出现真实需求再引入 `dataset_acl`。
