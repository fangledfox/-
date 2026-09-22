"""
server.py — 二经知识库本地服务
- 静态托管 portal/ 目录
- /api/* 接口读 scan/*.json，提供表/过程/知识库查询与写入
- 所有写操作先快照再落地
"""
from __future__ import annotations
import json
import shutil
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from parse_ddl import ingest as ingest_ddl

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "portal"
SCAN = ROOT / "scan"
KB = ROOT / "kb"
SNAPSHOTS = SCAN / "_snapshots"
SNAPSHOTS.mkdir(parents=True, exist_ok=True)

with open(ROOT / "tools" / "config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)

READ_ROOTS = [ROOT]


def load_json(p: Path, default):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8-sig"))
    return default


def save_json(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def snapshot_file(p: Path):
    """写入前快照（保留最近 12 个）。"""
    if not p.exists():
        return
    name = f"{p.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    snap = SNAPSHOTS / name
    shutil.copy2(p, snap)
    snaps = sorted(SNAPSHOTS.glob(f"{p.stem}_*.json"))
    for old in snaps[:-12]:
        old.unlink()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_relative_to(ROOT):
            self.send_error(404)
            return
        ext = path.suffix.lower()
        mime = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(ext, "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        qs = parse_qs(u.query)

        if path == "/api/ping":
            return self._send_json({"ok": True, "project": CONFIG["project"]})

        if path == "/api/stats":
            tables = load_json(SCAN / "tables.json", {"tables": {}}).get("tables", {})
            procs = load_json(SCAN / "procs.json", {"procs": {}}).get("procs", {})
            lineage = load_json(SCAN / "lineage.json", {"edges": []}).get("edges", [])
            field_count = sum(len(t.get("fields", [])) for t in tables.values())
            cmt_count = sum(
                len(t.get("column_comments", {})) for t in tables.values()
            )
            return self._send_json({
                "tables": len(tables),
                "procs": len(procs),
                "fields": field_count,
                "field_comments": cmt_count,
                "lineage_edges": len(lineage),
            })

        if path == "/api/tables":
            tables = load_json(SCAN / "tables.json", {"tables": {}}).get("tables", {})
            q = qs.get("q", [""])[0].lower()
            sch = qs.get("schema", [""])[0].lower()
            items = []
            for t in tables.values():
                if sch and t["schema"] != sch:
                    continue
                if q and q not in t["fullname"] and q not in t.get("comment", "").lower():
                    continue
                items.append({
                    "fullname": t["fullname"],
                    "schema": t["schema"],
                    "table": t["table"],
                    "comment": t.get("comment", ""),
                    "fields": len(t.get("fields", [])),
                    "distributed_by": t.get("distributed_by", []),
                })
            items.sort(key=lambda x: x["fullname"])
            return self._send_json({"items": items})

        if path == "/api/table":
            name = qs.get("name", [""])[0].lower()
            tables = load_json(SCAN / "tables.json", {"tables": {}}).get("tables", {})
            if name not in tables:
                return self._send_json({"error": "not found"}, 404)
            return self._send_json(tables[name])

        if path == "/api/procs":
            procs = load_json(SCAN / "procs.json", {"procs": {}}).get("procs", {})
            q = qs.get("q", [""])[0].lower()
            items = []
            for p in procs.values():
                if q and q not in p.get("name", "").lower() and q not in p.get("desc", "").lower():
                    continue
                items.append({k: v for k, v in p.items() if k != "body"})
            items.sort(key=lambda x: x.get("name", ""))
            return self._send_json({"items": items})

        if path == "/api/kb":
            # 列出 kb/ 下的 md 条目
            items = []
            if KB.exists():
                for md in KB.rglob("*.md"):
                    rel = md.relative_to(KB).as_posix()
                    items.append({"path": rel, "title": md.stem})
            return self._send_json({"items": sorted(items, key=lambda x: x["path"])})

        # 静态文件
        if path == "/" or path == "":
            path = "/index.html"
        fp = (PORTAL / path.lstrip("/")).resolve()
        try:
            fp.relative_to(PORTAL.resolve())
        except ValueError:
            return self.send_error(403)
        return self._send_file(fp)

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body)
        except Exception:
            return self._send_json({"error": "bad json"}, 400)

        if u.path == "/api/import-ddl":
            sql = data.get("sql", "")
            if not sql.strip():
                return self._send_json({"error": "empty"}, 400)
            snap_target = SCAN / "tables.json"
            snapshot_file(snap_target)
            result = ingest_ddl(sql)
            return self._send_json({"ok": True, **result})

        if u.path == "/api/comment":
            # {"table": "dw2.dw_user_base_info_ds", "column": "phone_no", "comment": "..."}
            name = data.get("table", "").lower()
            col = data.get("column", "").lower()
            cmt = data.get("comment", "")
            if not name or not col:
                return self._send_json({"error": "missing args"}, 400)
            p = SCAN / "tables.json"
            snapshot_file(p)
            db = load_json(p, {"tables": {}})
            t = db["tables"].get(name)
            if not t:
                return self._send_json({"error": "table not found"}, 404)
            t.setdefault("column_comments", {})[col] = cmt
            save_json(p, db)
            return self._send_json({"ok": True})

        return self.send_error(404)


def main():
    host = CONFIG["server"]["host"]
    port = CONFIG["server"]["port"]
    # 端口被占用就 +1
    import socket
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                break
            except OSError:
                port += 1
    print(f"二经知识库已启动: http://{host}:{port}")
    print("按 Ctrl+C 退出")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
