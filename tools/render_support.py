"""Render the per-operation support matrix from the distributable catalog."""

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
catalog = json.loads((ROOT / "src/yicloud/data/catalog.json").read_text(encoding="utf-8"))
rows = catalog["operations"]
counts = Counter(op["service"] for op in rows)
text = "# 公开接口支持矩阵\n\n基准 SDK v0.5.1，核对日期 2026-10-19。implemented-offline 描述实现及离线覆盖，不表示每项经过联机验证。真实 API、开发机生命周期及 SSH 的具体联测范围见 [api.md](api.md)。\n\n"
text += "服务统计：" + "，".join(f"{s}: {n}" for s, n in sorted(counts.items())) + "。\n\n"
text += "| 服务 | 操作 | 方法 / 实际路径 | 模式 | 状态 |\n|---|---|---|---|---|\n"
for op in rows:
    text += f"| {op['service']} | {op['action']} | `{op['method']} {op['path']}` | {op['response_mode']} | {op['status']} |\n"
text += "\n来源：[固定 SDK](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5)。内部工具函数不计入公开操作。\n"
(ROOT / "src/yicloud/skill/references/support.md").write_text(text, encoding="utf-8")
