"""生成溯源矩阵 traceability_matrix.json：把每个叶/图版、门户引用、公开/内部去向、
续权或换版时的影响面串起来。以 python -I 运行，只读现有清单与证据。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace")

from workbench.evidence import atomic_json, digest  # noqa: E402

WS = Path("/workspace")
leaf = json.loads((WS / "exhibition_assets/leaf_manifest.json").read_text(encoding="utf-8"))
img = json.loads((WS / "exhibition_assets/image_manifest.json").read_text(encoding="utf-8"))
browse = json.loads((WS / "evidence/downloads/browse-results.json").read_text(encoding="utf-8"))
records = {r["id"]: r for r in browse["records"]}

matrix = {
    "work": "HB-H2",
    "exhibition_window": ["2026-12-01", "2027-02-28"],
    "generated_from": [
        "exhibition_assets/leaf_manifest.json",
        "exhibition_assets/image_manifest.json",
        "evidence/downloads/browse-results.json",
    ],
    "leaves": [],
    "images": [],
    "rework_triggers": [],
}

for e in leaf:
    row = {
        "chapter": e["chapter"],
        "leaf": e["leaf"],
        "edition": e["edition"],
        "status": e["status"],
        "scan_record": e["scan_record"],
        "scan_reference": e["scan_reference"],
        "public_asset": e["public_asset"],
        "public_text_only_asset": e.get("public_text_only_asset"),
        "internal_asset": e["internal_asset"],
        "illustrations": e.get("illustrations", []),
        "continuity_note": e.get("continuity_note"),
    }
    matrix["leaves"].append(row)

for r in img:
    affected_leaves = [
        e["chapter"] + e["leaf"] for e in leaf if r["work"] in (e.get("illustrations") or [])
    ]
    trigger = None
    if r["work"] == "F3":
        trigger = "若 RIGHT-F3 续权至不早于 2027-02-28：重新评估 S6/fold1 公开，替换占位为原页"
    elif r["work"] == "F2":
        trigger = "若取得 F2 公开展陈许可（覆盖全展期、注明署名/裁切）：重新评估 S4/3v 公开"
    elif r["work"] == "F4":
        trigger = "F4 须先查明权利人并取得许可；在此之前 S9/ins1 维持留白，内部亦无使用依据"
    elif r["work"] == "F1":
        trigger = "F1 已公开可用；若许可变更，影响 S2/2v，须同步更新署名「合成摄影社」、禁止裁切条件"
    matrix["images"].append(
        {
            "work": r["work"],
            "rights_record": r["rights_record"],
            "rights_reference": r["rights_reference"],
            "public_eligible": r["public_eligible_full_exhibition"],
            "internal_eligible": r["internal_eligible_today"],
            "credit": r["credit_required"],
            "crop_allowed": r["crop_allowed"],
            "until": r["until"],
            "affected_leaves": affected_leaves,
            "rework_if_changed": trigger,
        }
    )
    if trigger:
        matrix["rework_triggers"].append({"work": r["work"], "action": trigger})

# 换版影响：若未来出现 1948 4v 的等价证明
matrix["rework_triggers"].append(
    {
        "work": "leaf:4v",
        "action": (
            "仅当出现 1948 4v 原叶或馆藏出具 equivalent=true 的等价证明时，"
            "才可替换 placeholder-4v；当前 EQ 证明 1952 S10 不等价，维持留白"
        ),
    }
)

out = WS / "state/traceability_matrix.json"
atomic_json(out, matrix)
print(json.dumps({"output": str(out), "leaves": len(matrix["leaves"]),
                  "images": len(matrix["images"]), "triggers": len(matrix["rework_triggers"])},
                 ensure_ascii=False))
