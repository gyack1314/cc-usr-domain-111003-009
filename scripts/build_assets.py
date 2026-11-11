"""第二至四章素材整理流水线。

输入：浏览器实地浏览并下载的证据目录（evidence/downloads），不读取门户数据种子推断状态。
输出：exhibition_assets（公开素材）与 internal_research（内部研究副本）两套独立目录，
以及逐叶、逐图引用清单和连续性/许可判定。所有判定基于门户记录 编号@SHA256 引用，可回溯。

以 python -I 运行；工作区路径在脚本内显式加入 sys.path。
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "/workspace")

from workbench.domain import coverage, leaf_key, licensed  # noqa: E402
from workbench.evidence import Journal, atomic_json, digest  # noqa: E402

WORKSPACE = Path("/workspace")
EVIDENCE = WORKSPACE / "evidence/downloads"
PUBLIC_DIR = WORKSPACE / "exhibition_assets"
INTERNAL_DIR = WORKSPACE / "internal_research"
JOURNAL = WORKSPACE / "state/journal/worklog.sqlite3"

# 展陈申请窗口（materials/request.md、materials/policy.md）
EXHIBITION_USE = "公开展陈"
INTERNAL_USE = "内部研究"
EXHIBITION_START = "2026-12-01"
EXHIBITION_END = "2027-02-28"
TODAY = "2026-11-12"

CHAPTER_TITLE = {"二": "第二章", "三": "第三章", "四": "第四章"}
# materials/chapters.csv 的 1948 期望叶序
EXPECTED = {
    "二": ["2r", "2v", "3r", "3v"],
    "三": ["4r", "4v", "fold1"],
    "四": ["5r", "5v", "ins1"],
}


def load_evidence():
    browse = json.loads((EVIDENCE / "browse-results.json").read_text(encoding="utf-8"))
    records = {r["id"]: r for r in browse["records"]}
    # 交叉校验：附件文件仍在且摘要一致
    for r in browse["records"]:
        att = EVIDENCE / r["attachment"]
        doc = EVIDENCE / r["document"]
        assert digest(att.read_bytes()) == r["record_sha256"], f"{r['id']} 附件摘要漂移"
        assert digest(doc.read_bytes()) == r["document_sha256"], f"{r['id']} 文书摘要漂移"
    return browse, records


def parse_rights(records):
    rights = {}
    for rid, r in records.items():
        if r["category"] in ("许可", "说明") and r["fields"].get("work", "").startswith("F"):
            f = r["fields"]
            rights[f["work"]] = {
                "record_id": rid,
                "reference": r["reference"],
                "uses": f.get("uses", []),
                "until": f.get("until"),
                "credit": f.get("credit"),
                "crop": f.get("crop"),
                "category": r["category"],
            }
    text_grant = next(
        r for r in records.values() if r["id"] == "RIGHT-T"
    )
    return rights, text_grant


def evaluate_image(work, rights):
    """返回 (公开可用?, 内部可用?, 判定说明列表)。许可按用途、期限、署名、裁切分别解释。"""
    g = rights.get(work)
    notes = []
    if g is None:
        return False, False, ["无任何许可记录"]
    if not g["uses"]:
        notes.append(
            f"{g['record_id']} 记载权属未明（uses 为空、无署名主体），任何用途均未获准"
        )
        return False, False, notes
    grant_for_licensed = {"uses": g["uses"], "until": g["until"] or ""}
    # 公开：必须覆盖整个展期至末日
    pub = (
        EXHIBITION_USE in g["uses"]
        and licensed(grant_for_licensed, EXHIBITION_USE, EXHIBITION_END)
    )
    if EXHIBITION_USE in g["uses"] and not pub:
        notes.append(
            f"含公开展陈用途但许可至 {g['until']}，早于展期末日 {EXHIBITION_END}，"
            "不覆盖整个展期，公开目录暂不收录"
        )
    elif pub:
        notes.append(f"公开展陈许可覆盖完整展期（至 {g['until']}）")
    elif EXHIBITION_USE not in g["uses"]:
        notes.append("许可用途不含公开展陈，内部研究权限不能转为展板公开权限")
    # 内部：以当前评估日判断期限
    internal = (
        INTERNAL_USE in g["uses"]
        and licensed(grant_for_licensed, INTERNAL_USE, TODAY)
    )
    if INTERNAL_USE in g["uses"] and not internal:
        notes.append(f"内部研究期限已于 {g['until']} 届满")
    return pub, internal, notes


def wrap_cjk(text, width=34):
    """按显示宽度折行（合成素材以中日韩字符为主，按字符数粗分行）。"""
    lines, cur = [], ""
    for ch in str(text):
        cur += ch
        if len(cur) >= width:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines or [""]


def placeholder_svg(title_lines, reason_lines, filename_note):
    """生成合法的文字占位 SVG（明确标注留白原因，不伪造任何历史画面）。"""
    head = "".join(
        f'<text x="64" y="{120 + i * 48}" font-size="26" fill="#7c2d12">{escape(t)}</text>'
        for i, t in enumerate(title_lines)
    )
    wrapped = []
    for line in reason_lines:
        wrapped.extend(wrap_cjk(line))
    body = "".join(
        f'<text x="64" y="{300 + i * 38}" font-size="20" fill="#475569">{escape(t)}</text>'
        for i, t in enumerate(wrapped)
    )
    note = "".join(
        f'<text x="64" y="{1060 + i * 34}" font-size="18" fill="#9a3412">{escape(t)}</text>'
        for i, t in enumerate(wrap_cjk(filename_note, width=46))
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1200" '
        'viewBox="0 0 900 1200">'
        '<rect width="900" height="1200" fill="#fff7ed" stroke="#c2410c" stroke-width="6" '
        'stroke-dasharray="18 12"/>'
        + head
        + body
        + note
        + "</svg>"
    )


def text_only_svg(chapter_title, leaf, scan_id, restriction_reasons):
    """公开文字版：保留该叶文字身份信息，图位以留白框和限制说明替代，不含任何受限图像画面。"""
    lines = [
        f"海湾港区建设史 · 公开文字版（剥离受限图版）",
        f"1948版 · {chapter_title} · 叶面 {leaf} · 源自扫描 {scan_id}",
        "正文文字使用许可：RIGHT-T，署名「海湾档案馆」，公开展陈有效期至 2027-12-31",
        "本件仅为文字信息副本，不复制原扫描中的任何照片画面；以下图位在公开素材中留白。",
    ]
    head_lines = []
    for i, t in enumerate(lines):
        wrapped = wrap_cjk(t, width=33)
        for j, part in enumerate(wrapped):
            head_lines.append((part, 28 if i == 0 and j == 0 else 24))
    head = "".join(
        f'<text x="64" y="{100 + i * 40}" font-size="{size}" fill="#243747">{escape(t)}</text>'
        for i, (t, size) in enumerate(head_lines)
    )
    reason_wrapped = []
    for r in restriction_reasons:
        reason_wrapped.extend(wrap_cjk(r, width=40))
    reason = "".join(
        f'<text x="96" y="{560 + i * 34}" font-size="18" fill="#7c2d12">{escape(t)}</text>'
        for i, t in enumerate(reason_wrapped)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="1200" viewBox="0 0 900 1200">'
        '<rect width="900" height="1200" fill="#ffffff"/>' + head
        + '<rect x="64" y="360" width="772" height="360" fill="#f8fafc" stroke="#c2410c" '
        'stroke-width="4" stroke-dasharray="16 10"/>'
        '<text x="450" y="530" font-size="26" fill="#9a3412" text-anchor="middle">图位留白（公开许可不足，禁止放置原图）</text>'
        + reason
        + '<text x="64" y="1080" font-size="18" fill="#475569">文字占位/文字版为合法替代，不构成授权补正，亦不修补缺失历史内容。</text>'
        "</svg>"
    )


def escape(s):
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def main():
    browse, records = load_evidence()
    rights, text_grant = parse_rights(records)
    journal = Journal(JOURNAL)

    # 只采用 1948 版扫描；1952 单独登记
    scans_1948 = sorted(
        (r for r in browse["records"] if r["category"] == "扫描" and r["fields"]["edition"] == "1948"),
        key=lambda r: leaf_key(r["fields"]["leaf"]),
    )
    scans_1952 = [
        r for r in browse["records"] if r["category"] == "扫描" and r["fields"]["edition"] == "1952"
    ]
    observed_leaves = [r["fields"]["leaf"] for r in scans_1948]
    expected_all = [leaf for ch in ("二", "三", "四") for leaf in EXPECTED[ch]]

    cov = coverage(expected_all, observed_leaves)
    eq_record = records["EQ"]
    assert eq_record["fields"]["equivalent"] is False

    # 准备干净目录
    for d in (PUBLIC_DIR, INTERNAL_DIR):
        if d.exists():
            for p in sorted(d.rglob("*"), reverse=True):
                if p.is_file() or p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    p.rmdir()
    (PUBLIC_DIR / "leaves").mkdir(parents=True)
    (INTERNAL_DIR / "leaves").mkdir(parents=True)
    (INTERNAL_DIR / "restricted_images").mkdir(parents=True)

    leaf_manifest = []
    image_manifest = []
    public_files = set()
    internal_files = set()

    for ch in ("二", "三", "四"):
        for leaf in EXPECTED[ch]:
            key = leaf_key(leaf)
            match = next(
                (r for r in scans_1948 if r["fields"]["leaf"] == leaf and r["fields"]["chapter"] == ch),
                None,
            )
            base_entry = {
                "chapter": CHAPTER_TITLE[ch],
                "leaf": leaf,
                "leaf_key": key,
                "edition": "1948",
                "expected_in": "materials/chapters.csv",
            }
            if match is None:
                # 缺叶：核验异版补页等价性
                alt = next(
                    (r for r in scans_1952 if r["fields"]["leaf"] == leaf), None
                )
                alt_note = "无任何异版扫描"
                if alt:
                    alt_note = (
                        f"存在 1952 异版 {alt['id']}（{alt['reference']}），但馆藏等价记录 "
                        f"{eq_record['id']}（{eq_record['reference']}）证明 equivalent=false："
                        f"{eq_record['fields']['reason']}，不得替代；该异版仅登记于内部研究目录"
                    )
                ph_name = f"leaves/placeholder-{leaf}.svg"
                ph_path = PUBLIC_DIR / ph_name
                ph_svg = placeholder_svg(
                    [f"留白占位 · {CHAPTER_TITLE[ch]} · 1948版 · 叶面 {leaf}"],
                    [
                        f"该叶在 1948 完整本扫描中缺失（领域工具 coverage 判定 missing）。",
                        alt_note,
                        "依业务规程不得伪造或以无等价证明的异版补齐，展板此处必须留白。",
                    ],
                    "本文件为文字占位，非历史文献扫描件，不承载任何原图内容。",
                )
                ph_path.write_text(ph_svg, encoding="utf-8")
                public_files.add(ph_name)
                leaf_manifest.append(
                    {
                        **base_entry,
                        "status": "missing",
                        "scan_record": None,
                        "scan_reference": None,
                        "public_asset": ph_name,
                        "public_asset_sha256": digest(ph_svg.encode("utf-8")),
                        "internal_asset": None,
                        "continuity_note": alt_note,
                    }
                )
                continue

            src = EVIDENCE / match["document"]
            illustrations = match["fields"]["illustrations"]
            # 页面公开可用性：正文文字许可 AND 页面所含每幅图均公开可用
            text_ok = licensed(
                {"uses": text_grant["fields"]["uses"], "until": text_grant["fields"]["until"]},
                EXHIBITION_USE,
                EXHIBITION_END,
            )
            image_decisions = {}
            for w in illustrations:
                pub, internal, notes = evaluate_image(w, rights)
                image_decisions[w] = {"public": pub, "internal": internal, "notes": notes}
            page_public = text_ok and all(d["public"] for d in image_decisions.values())

            leaf_name = f"leaves/{match['id']}-1948-{ch}-{leaf}.svg"
            internal_path = INTERNAL_DIR / leaf_name
            internal_path.write_bytes(src.read_bytes())
            internal_files.add(leaf_name)

            entry = {
                **base_entry,
                "status": "observed",
                "scan_record": match["id"],
                "scan_reference": match["reference"],
                "document_sha256": match["document_sha256"],
                "illustrations": illustrations,
                "image_decisions": image_decisions,
                "internal_asset": leaf_name,
                "internal_asset_sha256": digest(internal_path.read_bytes()),
            }

            if page_public:
                pub_path = PUBLIC_DIR / leaf_name
                pub_path.write_bytes(src.read_bytes())
                public_files.add(leaf_name)
                entry["public_asset"] = leaf_name
                entry["public_asset_sha256"] = digest(pub_path.read_bytes())
                entry["continuity_note"] = "1948 本版扫描，正文与所含图版许可均满足公开条件"
            else:
                reasons = []
                for w, d in image_decisions.items():
                    if not d["public"]:
                        reasons.extend([f"{w}：{n}" for n in d["notes"]])
                ph_name = f"leaves/placeholder-{match['id']}-{leaf}.svg"
                ph_path = PUBLIC_DIR / ph_name
                ph_svg = placeholder_svg(
                    [f"留白占位 · {CHAPTER_TITLE[ch]} · 1948版 · 叶面 {leaf}（扫描 {match['id']}）"],
                    [
                        "本叶正文文字已获准公开展陈，但所含照片未取得覆盖完整展期的公开许可：",
                        *reasons,
                        "文字许可不自动涵盖照片；原图仅存内部研究副本，展板此图位必须留白或换用获准素材。",
                    ],
                    "本文件为文字占位，非历史文献扫描件，不承载任何原图内容。",
                )
                ph_path.write_text(ph_svg, encoding="utf-8")
                public_files.add(ph_name)
                # 合法文字版：仅承载该叶文字信息与图位留白说明，剥离受限图版画面
                text_name = f"leaves/{match['id']}-1948-{ch}-{leaf}-textonly.svg"
                text_svg = text_only_svg(
                    CHAPTER_TITLE[ch], leaf, match["id"], reasons
                )
                (PUBLIC_DIR / text_name).write_text(text_svg, encoding="utf-8")
                public_files.add(text_name)
                entry["public_asset"] = ph_name
                entry["public_asset_sha256"] = digest(ph_svg.encode("utf-8"))
                entry["public_text_only_asset"] = text_name
                entry["public_text_only_sha256"] = digest(text_svg.encode("utf-8"))
                entry["continuity_note"] = "；".join(reasons)
            leaf_manifest.append(entry)

    # 逐图清单：F1-F4
    for w in ("F1", "F2", "F3", "F4"):
        pub, internal, notes = evaluate_image(w, rights)
        g = rights[w]
        on_leaves = [
            r["id"]
            for r in scans_1948
            if w in r["fields"]["illustrations"]
        ]
        row = {
            "work": w,
            "rights_record": g["record_id"],
            "rights_reference": g["reference"],
            "uses_granted": g["uses"],
            "until": g["until"],
            "credit_required": g["credit"],
            "crop_allowed": g["crop"],
            "appears_on_scans": on_leaves,
            "public_eligible_full_exhibition": pub,
            "internal_eligible_today": internal,
            "decision_notes": notes,
        }
        if pub:
            row["public_handling"] = (
                f"可入公开目录；署名「{g['credit']}」；"
                + ("允许裁切但不得改变图意" if g["crop"] else "禁止裁切")
            )
        else:
            row["public_handling"] = "不进入公开目录；公开图位以文字占位留白，建议替换为获准素材"
        image_manifest.append(row)
        # 内部图版登记：公开未获准的图版建立受限指针；F1 虽公开可用，内部副本仍按许可条件登记
        if not pub:
            pointer = INTERNAL_DIR / "restricted_images" / f"{w}-RESTRICTED.json"
            atomic_json(
                pointer,
                {
                    "work": w,
                    "restriction": "内部研究专用，禁止经销、外部印刷与任何公开展陈",
                    "source_leaves": [
                        f"leaves/{r['id']}-1948-{r['fields']['chapter']}-{r['fields']['leaf']}.svg"
                        for r in scans_1948
                        if w in r["fields"]["illustrations"]
                    ],
                    "rights_reference": g["reference"],
                    "credit_required": g["credit"],
                    "crop_allowed": g["crop"],
                    "until": g["until"],
                    "notes": notes,
                },
            )
            internal_files.add(f"restricted_images/{w}-RESTRICTED.json")
        else:
            journal.append(
                f"image:{w}:public-ok",
                {
                    "work": w,
                    "rights_reference": g["reference"],
                    "credit": g["credit"],
                    "crop_allowed": g["crop"],
                    "note": "公开可用图版，内部副本与公开目录均按同一署名/裁切条件使用",
                },
            )

    # 1952 异版单独内部登记，不进公开
    for r in scans_1952:
        name = f"leaves/{r['id']}-1952-{r['fields']['chapter']}-{r['fields']['leaf']}.svg"
        (INTERNAL_DIR / name).write_bytes((EVIDENCE / r["document"]).read_bytes())
        internal_files.add(name)

    # 连续性总说明
    continuity = {
        "basis": "期望叶序取自 materials/chapters.csv（1948 完整本 H48），观测叶序取自浏览器实地浏览的门户扫描记录",
        "domain_coverage_result": cov,
        "expected_leaves": expected_all,
        "observed_1948_leaves": observed_leaves,
        "missing": cov["missing"],
        "duplicate_scans": cov["duplicate"],
        "extra_edition_scans": [
            {
                "record_id": r["id"],
                "reference": r["reference"],
                "edition": r["fields"]["edition"],
                "leaf": r["fields"]["leaf"],
                "disposition": "仅内部研究登记；EQ 证明与 1948 同叶名不等价，禁止用于补缺",
            }
            for r in scans_1952
        ],
        "equivalence_evidence": {
            "record_id": eq_record["id"],
            "reference": eq_record["reference"],
            "equivalent": False,
            "reason": eq_record["fields"]["reason"],
        },
        "fold_and_insert_note": (
            "fold1（折页）与 ins1（插页）各为单个叶面身份，不以文件数量计完整；"
            "r/v 为同一叶的正反面，印刷页码不作为身份"
        ),
        "per_chapter": [
            {
                "chapter": CHAPTER_TITLE[ch],
                "expected": EXPECTED[ch],
                "observed": [
                    r["fields"]["leaf"]
                    for r in scans_1948
                    if r["fields"]["chapter"] == ch
                ],
                "missing": coverage(EXPECTED[ch], [
                    r["fields"]["leaf"] for r in scans_1948 if r["fields"]["chapter"] == ch
                ])["missing"],
            }
            for ch in ("二", "三", "四")
        ],
    }

    atomic_json(PUBLIC_DIR / "leaf_manifest.json", leaf_manifest)
    atomic_json(PUBLIC_DIR / "image_manifest.json", image_manifest)
    atomic_json(INTERNAL_DIR / "leaf_manifest.json", leaf_manifest)
    atomic_json(INTERNAL_DIR / "image_manifest.json", image_manifest)
    atomic_json(INTERNAL_DIR / "continuity.json", continuity)

    # 版本化构建键：进度账只追加，重建以新版本键记录并注明接续关系
    existing = [n["key"] for n in journal.read() if n["key"].startswith("build:assets-v")]
    run_version = 1
    if existing:
        run_version = max(int(k.rsplit("-v", 1)[1]) for k in existing) + 1
    journal.append(
        f"build:assets-v{run_version}",
        {
            "supersedes": f"build:assets-v{run_version - 1}" if run_version > 1 else None,
            "inputs": {
                "browse_results": str(EVIDENCE / "browse-results.json"),
                "browse_sha256": digest((EVIDENCE / "browse-results.json").read_bytes()),
            },
            "coverage": cov,
            "public_file_count": len(public_files),
            "internal_file_count": len(internal_files),
            "public_dir": str(PUBLIC_DIR),
            "internal_dir": str(INTERNAL_DIR),
            "exhibition_window": [EXHIBITION_START, EXHIBITION_END],
        },
    )
    print(json.dumps(
        {
            "coverage": cov,
            "public_files": sorted(public_files),
            "internal_files": sorted(internal_files),
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
