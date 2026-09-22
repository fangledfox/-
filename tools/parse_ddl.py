"""
parse_ddl.py — 解析单条或多条 GP/PostgreSQL CREATE TABLE 语句。
输入：一段 SQL 文本（用户从 pgAdmin / 建表脚本里复制出来的）。
输出：tables.json 增量结构（表名 → schema / 字段 / 分布键 / 表注释 / 列注释）。

设计原则：
- 只做"够用"的解析，不追求完整 SQL 语法树；
- 括号配平切字段，处理 character varying(30)、numeric(10,2)、character(1) 等带括号类型；
- COMMENT ON TABLE / COMMENT ON COLUMN 单独抽取；
- 分区子表自动归并父表（_1_prt_pYYYYMMDD 之类的后缀剥掉）。
"""
from __future__ import annotations
import re
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
TABLES_JSON = ROOT / "scan" / "tables.json"


def normalize_table_name(name: str) -> str:
    """分区子表归并到父表：dw_user_base_info_ds_1_prt_p20260831 → dw_user_base_info_ds"""
    name = name.strip().strip('"').lower()
    # 去掉分区子表后缀 _1_prt_p20260831 / _1_prt_p202608 / _1_prt_default
    name = re.sub(r"_1_prt_p\d+$", "", name)
    name = re.sub(r"_1_prt_\w+$", "", name)
    return name


def split_schema_table(qualified: str) -> tuple[str, str]:
    qualified = qualified.strip().strip('"')
    if "." in qualified:
        sch, tbl = qualified.split(".", 1)
        return sch.strip().lower(), tbl.strip().lower()
    return "public", qualified.lower()


def _split_fields(body: str) -> list[str]:
    """括号配平切字段：处理 character varying(30)、numeric(10,2) 等带括号类型。"""
    fields = []
    depth = 0
    cur = []
    in_str = False
    escape = False
    for ch in body:
        if in_str:
            cur.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_str = False
            continue
        if ch == "'":
            in_str = True
            cur.append(ch)
            continue
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            fields.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        fields.append(tail)
    return fields


_KEYWORDS = re.compile(
    r"\s+(NOT\s+NULL|NULL|DEFAULT|PRIMARY|UNIQUE|CHECK|REFERENCES|"
    r"COLLATE|ENCODED|COLUMN|ENCODING|STORAGE|COMPRESS|DISTKEY|SORTKEY|CONSTRAINT|"
    r"AUTO_INCREMENT|GENERATED)\b",
    re.IGNORECASE,
)


def parse_field_line(line: str) -> dict | None:
    """从一行字段定义里抽字段名 / 类型 / 是否可空。"""
    line = line.strip().rstrip(",").strip()
    if not line:
        return None
    upper = line.upper()
    # 跳过约束行
    if upper.startswith((
        "PRIMARY KEY", "UNIQUE", "CONSTRAINT", "CHECK", "FOREIGN KEY",
        "DISTRIBUTED", "SORT", "WITH (",
    )):
        return None
    # 第一个 token 是字段名，剩下是类型+约束
    parts = line.split(None, 1)
    if len(parts) < 2:
        return None
    name = parts[0].strip().strip('"').lower()
    rest = parts[1].strip()
    m = _KEYWORDS.search(rest)
    ftype = rest[: m.start()] if m else rest
    ftype = re.sub(r"\s+", " ", ftype.strip().lower())
    nullable = "NOT NULL" not in upper
    return {"name": name, "type": ftype, "nullable": nullable}


def parse_create_table(sql: str) -> list[dict]:
    """解析一段 SQL 里所有 CREATE TABLE，返回表字典列表。"""
    tables = []
    # 找到每个 CREATE TABLE [IF NOT EXISTS] name ( ... )
    for m in re.finditer(
        r'CREATE\s+(?:WRITABLE\s+|READABLE\s+)?(?:FOREIGN\s+)?TABLE\s+'
        r'(?:IF\s+NOT\s+EXISTS\s+)?["\']?([\w.]+)["\']?\s*\(',
        sql,
        re.IGNORECASE,
    ):
        qualified = m.group(1)
        start = m.end()
        depth = 1
        i = start
        in_str = False
        escape = False
        while i < len(sql) and depth > 0:
            ch = sql[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == "'":
                    in_str = False
                i += 1
                continue
            if ch == "'":
                in_str = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        body = sql[start : i - 1]
        tail = sql[i : i + 400]
        # 分布键
        dist = []
        dm = re.search(r"DISTRIBUTED\s+BY\s*\(([^)]+)\)", tail, re.IGNORECASE)
        if dm:
            dist = [c.strip().strip('"').lower() for c in dm.group(1).split(",")]
        elif re.search(r"DISTRIBUTED\s+RANDOMLY", tail, re.IGNORECASE):
            dist = ["<random>"]
        sch, tbl = split_schema_table(qualified)
        tbl = normalize_table_name(tbl)
        fields = []
        for fl in _split_fields(body):
            parsed = parse_field_line(fl)
            if parsed:
                fields.append(parsed)
        tables.append(
            {
                "schema": sch,
                "table": tbl,
                "fullname": f"{sch}.{tbl}",
                "fields": fields,
                "distributed_by": dist,
                "comment": "",
                "column_comments": {},
                "source": "manual",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )
    return tables


def parse_comments(sql: str, tables: dict) -> None:
    """解析 COMMENT ON TABLE / COMMENT ON COLUMN。"""
    for m in re.finditer(
        r"COMMENT\s+ON\s+TABLE\s+[\"']?([\w\.]+)[\"']?\s+IS\s+'((?:[^'\\]|\\.)*)'",
        sql,
        re.IGNORECASE,
    ):
        qualified, cmt = m.group(1), m.group(2).replace("''", "'")
        sch, tbl = split_schema_table(qualified)
        tbl = normalize_table_name(tbl)
        key = f"{sch}.{tbl}"
        if key in tables:
            tables[key]["comment"] = cmt
    for m in re.finditer(
        r"COMMENT\s+ON\s+COLUMN\s+[\"']?([\w\.]+)[\"']?\.([\w$]+)[\"']?\s+IS\s+'((?:[^'\\]|\\.)*)'",
        sql,
        re.IGNORECASE,
    ):
        qualified, col, cmt = m.group(1), m.group(2).lower(), m.group(3).replace("''", "'")
        sch, tbl = split_schema_table(qualified)
        tbl = normalize_table_name(tbl)
        key = f"{sch}.{tbl}"
        if key in tables:
            tables[key].setdefault("column_comments", {})[col] = cmt


def ingest(sql: str, merge: bool = True) -> dict:
    """把一段 SQL 并入 tables.json。返回 {added, updated, total}。"""
    if TABLES_JSON.exists():
        db = json.loads(TABLES_JSON.read_text(encoding="utf-8-sig"))
    else:
        db = {"tables": {}}
    tables = db.setdefault("tables", {})
    added = updated = 0
    for t in parse_create_table(sql):
        key = t["fullname"]
        if key in tables:
            updated += 1
            # 保留人工补的注释，新解析覆盖结构
            old_cmt = tables[key].get("column_comments", {})
            t["column_comments"] = {**old_cmt, **t.get("column_comments", {})}
        else:
            added += 1
        tables[key] = {**tables.get(key, {}), **t}
    # 注释二次扫（可能在 CREATE TABLE 之后）
    parse_comments(sql, tables)
    db["total"] = len(tables)
    TABLES_JSON.write_text(
        json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"added": added, "updated": updated, "total": len(tables)}


if __name__ == "__main__":
    # 命令行调试：python parse_ddl.py <file.sql>
    import sys

    if len(sys.argv) > 1:
        content = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
        result = ingest(content)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法: python parse_ddl.py <ddl_file.sql>")
