"""发布前独立校验：清单指纹一致性 + 公开目录隔离性（不得含任何内部专用文件）。

以 python -I 运行。校验只读，不修改素材。任一不过即以非零码退出并打印问题。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace")

from workbench.evidence import digest  # noqa: E402

WS = Path("/workspace")
PUB = WS / "exhibition_assets"
INT = WS / "internal_research"

# 公开目录绝不能出现的内部专用身份
FORBIDDEN_SCAN_IDS = ["S4", "S6", "S9", "S10"]  # 含 F2/F3/F4 的原页与 1952 异版
FORBIDDEN_MARKERS = ["RESTRICTED"]


def fail(issues, msg):
    issues.append(msg)


def main():
    issues = []
    pub_leaf = json.loads((PUB / "leaf_manifest.json").read_text(encoding="utf-8"))
    pub_img = json.loads((PUB / "image_manifest.json").read_text(encoding="utf-8"))
    int_leaf = json.loads((INT / "leaf_manifest.json").read_text(encoding="utf-8"))
    int_img = json.loads((INT / "image_manifest.json").read_text(encoding="utf-8"))

    if pub_leaf != int_leaf:
        fail(issues, "两套目录的 leaf_manifest 不一致")
    if pub_img != int_img:
        fail(issues, "两套目录的 image_manifest 不一致")

    pub_files = {p.relative_to(PUB).as_posix() for p in PUB.rglob("*") if p.is_file()}
    int_files = {p.relative_to(INT).as_posix() for p in INT.rglob("*") if p.is_file()}

    # 1) 清单登记的公开文件必须存在且指纹一致
    listed_public = set()
    for e in pub_leaf:
        asset = e.get("public_asset")
        if asset:
            listed_public.add(asset)
            fp = PUB / asset
            if not fp.is_file():
                fail(issues, f"清单公开文件缺失：{asset}")
            elif digest(fp.read_bytes()) != e.get("public_asset_sha256"):
                fail(issues, f"公开文件指纹不符：{asset}")
        to = e.get("public_text_only_asset")
        if to:
            listed_public.add(to)
            fp = PUB / to
            if not fp.is_file():
                fail(issues, f"文字版缺失：{to}")
            elif digest(fp.read_bytes()) != e.get("public_text_only_sha256"):
                fail(issues, f"文字版指纹不符：{to}")

    # 2) 公开目录实际文件必须都在清单或文档范围内（防游离文件）
    docs = {"README.md", "策展说明.md", "leaf_manifest.json", "image_manifest.json"}
    unlisted = pub_files - listed_public - docs
    if unlisted:
        fail(issues, f"公开目录存在清单外游离文件：{sorted(unlisted)}")

    # 3) 内部专用文件不得出现在公开目录
    for name in pub_files:
        for sid in FORBIDDEN_SCAN_IDS:
            # 仅拦截原始扫描页文件名；占位/文字版允许在说明文字中引用编号
            if name.startswith(f"leaves/{sid}-") and "textonly" not in name:
                fail(issues, f"内部专用扫描页混入公开目录：{name}")
        for marker in FORBIDDEN_MARKERS:
            if marker in name:
                fail(issues, f"内部受限指针混入公开目录：{name}")

    # 4) 公开目录的 SVG 内容不得承载受限原页画面：
    #    原始扫描 SVG 带固定馆藏抬头与图版引用；文字版/占位不得出现 F2/F3/F4 的「图版引用」画面行
    for fp in (PUB / "leaves").glob("*.svg"):
        text = fp.read_text(encoding="utf-8")
        if "textonly" in fp.name or "placeholder" in fp.name:
            # 合法替代件只能以说明文字提到 F2/F3/F4，绝不能是原始扫描版式
            if "馆藏图示 · 内容使用应核对独立许可" in text:
                fail(issues, f"替代件疑似含原始扫描画面：{fp.name}")
        else:
            # 直接公开的原始扫描页：其图版只能是公开可用的 F1 或无图版
            for bad in ("图版引用：F2", "图版引用：F3", "图版引用：F4"):
                if bad in text:
                    fail(issues, f"公开扫描页含受限图版画面 {bad}：{fp.name}")

    # 5) 逐图判定与目录布局互相印证
    for row in pub_img:
        w = row["work"]
        if row["public_eligible_full_exhibition"]:
            if w != "F1":
                fail(issues, f"预期仅 F1 公开可用，实际 {w} 被标记公开")
        else:
            # 不公开图版不得有任何公开原始页
            for e in pub_leaf:
                if w in (e.get("illustrations") or []) and "textonly" not in (
                    e.get("public_asset") or ""
                ) and "placeholder" not in (e.get("public_asset") or ""):
                    fail(issues, f"{w} 未公开却存在非占位公开页：{e.get('public_asset')}")

    # 6) 署名条件回读：公开可用项必须具备署名主体
    for row in pub_img:
        if row["public_eligible_full_exhibition"] and not row["credit_required"]:
            fail(issues, f"{row['work']} 标记公开但缺少署名主体")

    # 7) 内部目录应保留全部 1948 观测原页与 1952 异版
    for required in ("leaves/S10-1952-三-4v.svg", "restricted_images/F2-RESTRICTED.json",
                     "restricted_images/F3-RESTRICTED.json", "restricted_images/F4-RESTRICTED.json",
                     "continuity.json"):
        if required not in int_files:
            fail(issues, f"内部目录缺少应保留文件：{required}")

    result = {
        "checked_public_files": sorted(pub_files),
        "checked_internal_files": sorted(int_files),
        "issues": issues,
        "passed": not issues,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
