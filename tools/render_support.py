"""Render a local maintenance report; it is not part of the execution skill."""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "src/yicloud/data/catalog.json").read_text(encoding="utf-8"))
rows = catalog["operations"]
counts = Counter(op["service"] for op in rows)
text = "# 固定 SDK 接口支持矩阵\n\n基准 SDK v0.5.1。implemented-offline 描述实现及离线覆盖，不表示每项经过联机验证。此文件由工具生成，仅用于本地维护；日常操作使用 CLI 帮助与 api list。\n\n"
text += "服务统计：" + "，".join(f"{s}: {n}" for s, n in sorted(counts.items())) + "。\n\n"
text += "| 服务 | 操作 | 方法 / 实际路径 | 模式 | 状态 |\n|---|---|---|---|---|\n"
for op in rows:
    text += f"| {op['service']} | {op['action']} | `{op['method']} {op['path']}` | {op['response_mode']} | {op['status']} |\n"
text += "\n来源：[固定 SDK](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5)。内部工具函数不计入公开操作。\n"
report = ROOT / "docs/support-matrix.md"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(text, encoding="utf-8")
