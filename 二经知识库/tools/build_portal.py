"""
build_portal.py — 把 tools/portal_template.html 复制为 portal/index.html。
后续版本可以在这里注入中间层数据分片；当前骨架版本直接拷贝。
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "tools" / "portal_template.html"
OUT = ROOT / "portal" / "index.html"

OUT.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(TEMPLATE, OUT)
print(f"门户已生成: {OUT}")
