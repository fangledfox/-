# 二经知识库

省公司经分数据仓库（GP）的本地知识库：表字典、字段注释、存储过程、血缘、口径规范。

## 启动

双击 `启动二经知识库.bat`，浏览器自动打开 `http://127.0.0.1:8890`（端口被占会自动 +1）。

## 目录

```
二经知识库/
├─ 启动二经知识库.bat        # 双击启动
├─ tools/
│  ├─ config.json            # 配置（schema 分层、端口）
│  ├─ server.py              # 本地 HTTP 服务
│  ├─ build_portal.py        # 生成门户
│  ├─ portal_template.html   # 前端单文件模板
│  ├─ parse_ddl.py           # CREATE TABLE 解析
│  ├─ parse_proc.py          # （待补）过程解析
│  └─ parse_lineage.py       # （待补）血缘解析
├─ portal/                   # 产物 index.html
├─ scan/                     # 中间层
│  ├─ tables.json  procs.json  lineage.json
│  ├─ _sources/              # 源文件镜像
│  └─ _snapshots/            # 导入前快照
└─ kb/                       # 人工知识
   ├─ standards/             # 业务口径
   ├─ redlines/              # 开发红线
   ├─ sql_templates/         # SQL 模板
   └─ env/                   # 架构图
```

## 当前能力（v0.1 骨架）

- [x] 本地服务，双击启动
- [x] 粘贴 CREATE TABLE 自动解析入库
- [x] 表字典搜索 + schema 分层过滤
- [x] 字段中文注释补录（带快照）
- [ ] 存储过程解析与浏览
- [ ] 表级血缘
- [ ] 知识库 md 渲染
- [ ] 字段全局检索
- [ ] CSV/Markdown 导出

## 数据录入方式

环境无导出权限，靠手工逐步录入：

1. 从 pgAdmin 复制单张表的 `CREATE TABLE` + `COMMENT ON` 语句；
2. 打开浏览器 → 导入 → 粘贴 → 导入；
3. 表字典里点开表详情，补字段中文注释；
4. 过程和 SQL 后续按同样方式逐步灌。
