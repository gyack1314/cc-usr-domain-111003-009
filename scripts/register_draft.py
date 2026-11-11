"""通过浏览器在门户登记「公开素材范围」待审草稿，并回读核对状态、署名与目录摘要。

草稿引用全部取自浏览器实地浏览得到的 编号@SHA256；保存后重新打开草稿页回读，
并访问 /drafts 确认其处于「待人工审批」。以 python -I 运行。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace")

from playwright.sync_api import sync_playwright, expect  # noqa: E402

from workbench.evidence import Journal  # noqa: E402

BASE = "http://127.0.0.1:8765"
DRAFT_KEY = "HB-H2-exhibition-scope-ch2-4"

BODY = """公开素材范围登记（HB-H2 第二至四章，展期 2026-12-01 至 2027-02-28），状态：待人工审批。

一、可公开原始扫描页（1948 完整本 H48）：S1(2r)、S2(2v,含F1)、S3(3r)、S5(4r)、S7(5r)、S8(5v)。
二、仅公开文字版、图位留白：S4(3v, F2无公开权)、S6(fold1, F3公开许可2027-01-31到期不覆盖展期末日)、S9(ins1, F4权属未明)。
三、必须留白：1948 第三章 4v 缺叶；1952 异版 S10 经 EQ 证明不等价（删去船坞段），禁止补缺。
四、署名条件：正文 RIGHT-T 署名「海湾档案馆」；F1 署名「合成摄影社」且禁止裁切（crop=false）。
五、未获准图像 F2/F3/F4 一律不进公开目录；内部研究副本独立存放，不得外发或转公开。
本草稿不构成审批；馆员批准后方可对外使用。"""


def main():
    browse = json.loads(
        Path("/workspace/evidence/downloads/browse-results.json").read_text(encoding="utf-8")
    )
    refs_by_id = {r["id"]: r["reference"] for r in browse["records"]}
    ref_order = [
        "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10",
        "RIGHT-T", "RIGHT-F1", "RIGHT-F2", "RIGHT-F3", "RIGHT-F4", "EQ",
    ]
    refs = [refs_by_id[i] for i in ref_order]

    journal = Journal("/workspace/state/journal/worklog.sqlite3")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1280, "height": 1000})

        page.goto(f"{BASE}/draft/new", wait_until="domcontentloaded")
        page.get_by_label("草稿编号").fill(DRAFT_KEY)
        page.get_by_label("标题", exact=True).fill("HB-H2 第二至四章展板公开素材范围（待审）")
        page.get_by_label("正文", exact=True).fill(BODY)
        page.get_by_label("资料引用，每行一项 编号@摘要").fill("\n".join(refs))
        page.screenshot(path="/workspace/evidence/draft-before-save.png", full_page=True)
        page.get_by_role("button", name="保存预审草稿").click()
        page.wait_for_load_state("domcontentloaded")

        # 回读草稿详情
        expect(page).to_have_url(f"{BASE}/draft/{DRAFT_KEY}")
        status = page.get_by_test_id("draft-status").inner_text()
        title_val = page.get_by_label("标题", exact=True).input_value()
        body_val = page.get_by_label("正文", exact=True).input_value()
        refs_val = page.get_by_label("资料引用，每行一项 编号@摘要").input_value()
        page.screenshot(path="/workspace/evidence/draft-after-save.png", full_page=True)

        assert status == "待人工审批", f"草稿状态异常：{status}"
        assert title_val.startswith("HB-H2")
        assert "海湾档案馆" in body_val and "合成摄影社" in body_val
        assert "禁止裁切" in body_val
        saved_refs = [l for l in refs_val.splitlines() if l.strip()]
        assert saved_refs == refs, "回读引用与提交不一致"

        # /drafts 列表核对
        page.goto(f"{BASE}/drafts", wait_until="domcontentloaded")
        expect(page.get_by_role("link", name="HB-H2 第二至四章展板公开素材范围（待审）")).to_have_count(1)
        list_text = page.locator("main").inner_text()
        assert "待人工审批" in list_text
        page.screenshot(path="/workspace/evidence/draft-list.png", full_page=True)

        journal.append(
            "draft:public-scope-v1",
            {
                "draft_key": DRAFT_KEY,
                "status_readback": status,
                "ref_count": len(saved_refs),
                "credit_checks": ["海湾档案馆", "合成摄影社", "禁止裁切"],
                "summary_in_body": "可公开6页/文字版3页/缺叶4v留白/F2F3F4不进公开目录",
                "screenshots": [
                    "evidence/draft-before-save.png",
                    "evidence/draft-after-save.png",
                    "evidence/draft-list.png",
                ],
            },
        )
        browser.close()
    print(json.dumps({"draft_key": DRAFT_KEY, "status": status, "refs": len(refs)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
