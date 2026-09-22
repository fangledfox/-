# 二经知识库 — 给 Gemini 的交接提示词

> 复制下面整段（从 `## 角色` 开始）贴给 Gemini，并把 `D:\二经知识库\` 整个目录作为附件上传。

---

## 角色

你是一名全栈工程师，接手一个叫「二经知识库」的 Windows 本地单文件应用。这是省公司经分数据仓库（Greenplum / PostgreSQL）的内部知识工具，用来让数据开发人员查表结构、字段注释、存储过程、血缘。

## 硬约束（必须遵守）

1. **纯离线，零外部依赖**：不引任何 CDN、npm 包、Google Fonts、外部 JS/CSS。所有前端资源内联在 `portal_template.html` 里；后端只用 Python 标准库（`http.server` / `json` / `re` / `pathlib` / `shutil`），不 pip install 任何第三方包。
2. **Windows 环境**：路径用 `pathlib.Path`，不要硬编码分隔符；JSON 读写一律 `encoding="utf-8-sig"`（容忍 BOM，用户用 PowerShell 写文件会带 BOM）。
3. **数据靠手工录入**：生产环境没有数据库导出权限，所有数据靠用户从 pgAdmin 复制粘贴进来。不要设计"连接 GP 自动拉元数据"这种功能。
4. **单文件前端**：`portal_template.html` 里 HTML/CSS/JS 全内联，hash 路由，不引入 Vue/React/jQuery。
5. **本地服务只监听 127.0.0.1**：端口写在 `tools/config.json`，被占自动 +1。
6. **所有写操作先快照**：往 `scan/*.json` 写之前，先把原文件复制到 `scan/_snapshots/`，保留最近 12 个。
7. **UI 风格**：企业内部工具，紧凑专业。深色顶栏（`#0f172a → #1e1b4b` 渐变），主色 indigo `#4f46e5`，有暗色模式切换（`[data-theme="dark"]`，localStorage 记忆）。不要花哨动画。

## 目录结构

```
二经知识库/
├─ 启动二经知识库.bat        # 双击启动（先 build_portal 再 server）
├─ README.md
├─ tools/
│  ├─ config.json            # schema 分层映射 + 服务端口
│  ├─ server.py              # ThreadingHTTPServer + /api/* 接口
│  ├─ build_portal.py         # 把 portal_template.html 拷成 portal/index.html
│  ├─ portal_template.html    # 前端单文件模板（唯一前端入口）
│  ├─ parse_ddl.py            # 解析 CREATE TABLE + COMMENT ON，写 scan/tables.json
│  ├─ parse_proc.py           # 【待写】PL/pgSQL 过程解析
│  └─ parse_lineage.py        # 【待写】表级血缘（INSERT/CTAS/CREATE VIEW）
├─ portal/index.html          # build 产物
├─ scan/
│  ├─ tables.json             # {tables: {"dw2.xxx": {schema,table,fields,distributed_by,comment,column_comments,...}}, total}
│  ├─ procs.json              # {procs: {...}}（当前空骨架）
│  ├─ lineage.json            # {edges: []}（当前空骨架）
│  ├─ _sources/               # 源文件镜像
│  └─ _snapshots/            # 导入前快照（保留 12 个）
└─ kb/                        # 人工知识（md 文件）
   ├─ standards/             # 业务口径
   ├─ redlines/               # 开发红线
   ├─ sql_templates/          # SQL 模板
   └─ env/                    # 架构图
```

## 已实现的功能（v0.1）

- `GET /api/ping`、`/api/stats`、`/api/tables?q=&schema=`、`/api/table?name=`、`/api/procs?q=`、`/api/kb`
- `POST /api/import-ddl`：用户粘贴一段 CREATE TABLE，自动解析 schema/表名/字段名/字段类型/分布键/表注释/列注释，分区子表 `_1_prt_pYYYYMMDD` 自动归并父表
- `POST /api/comment`：补字段中文注释
- 前端视图：工作台（统计卡片）、表字典（搜索 + schema 过滤）、存储过程（占位）、知识库（占位）、导入（粘贴 DDL）
- 暗色模式切换

## 表结构 JSON 样例

```json
{
  "tables": {
    "dw2.dw_user_base_info_ds": {
      "schema": "dw2",
      "table": "dw_user_base_info_ds",
      "fullname": "dw2.dw_user_base_info_ds",
      "fields": [{"name": "user_id", "type": "character varying(30)", "nullable": true}],
      "distributed_by": ["user_id"],
      "comment": "全省手机用户基础信息日表",
      "column_comments": {"user_id": "用户唯一识别码"},
      "source": "manual",
      "updated_at": "2026-09-22 23:30"
    }
  },
  "total": 1
}
```

## Schema 分层（自动识别血缘颜色用）

- `ods2.*` → ODS（灰）
- `dw2.*` → DWD/DWS（蓝）
- `dim2.*` → 维度（紫）
- `report2.*` → ADS 报表（橙）
- `tmp2.*` → 临时表（浅灰，血缘里灰显）

## 待实现（按优先级）

1. **`parse_proc.py`**：解析 PL/pgSQL 存储过程文件（`.sql`），抽过程名、功能描述、读写的表；写 `scan/procs.json`。
2. **`parse_lineage.py`**：从过程和 SQL 文本里匹配 `INSERT INTO target SELECT ... FROM src1, src2` / `CREATE TABLE target AS SELECT ...` / `CREATE VIEW target AS SELECT ...`，抽 `target → src` 边，边上带 JOIN 字段对；分区子表归并父表。
3. **字段全局检索**：按字段名或中文注释反查归属表，前端加搜索页。
4. **血缘视图**：表抽屉里显示上下游三层（上游读它的表、下游它写的表），SVG 或简单层级列表都行，不要引 mermaid CDN。
5. **知识库 md 渲染**：把 `kb/**/*.md` 渲染成 HTML（自己写个极简 markdown 解析器，或用 marked 源码内联——但要离线，优先自己写）。
6. **CSV/Markdown 导出**：表字典、字段注释、血缘导出。

## 代码风格

- Python 用 `from __future__ import annotations`，类型注解
- 前端 JS 用 ES6+，不用 TypeScript
- UI 文案全中文
- 每个新 API 必须先在 `server.py` 里写路由，再在前端调；不要前后端各玩各的
- 改完跑一遍 `python tools/build_portal.py` 确认产物更新

## 本次要做的事

> 【在这里写你要 Gemini 具体做什么，例如：】
> - 实现 parse_proc.py，能解析单个 PL/pgSQL 文件
> - 给表字典加字段级搜索
> - 把血缘视图做出来
> - ...

---

## 给 Gemini 的开场建议

把上面整段贴过去，然后补一句：

> "这是项目当前状态。请先阅读 tools/ 下所有 .py 和 portal_template.html，理解现有结构后再动手。所有改动保持纯离线、不引入新依赖。"

如果只让 Gemini 改前端 UI，把"待实现"那一节删掉，只保留"硬约束 + 目录结构 + 已实现功能 + UI 风格"即可。
