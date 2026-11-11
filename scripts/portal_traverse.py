"""通过真实浏览器遍历本地门户：浏览目录、打开条目、下载 JSON 附件与扫描/文书副本。

脚本位于 /workspace/scripts，下载内容写入独立证据目录；使用 python -I 运行，
仅通过显式 sys.path 加载工作区代码，不依赖门户数据种子推断页面状态。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace")

from playwright.sync_api import sync_playwright  # noqa: E402

from workbench.evidence import Journal, digest  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("evidence_dir", type=Path)
    ap.add_argument("journal", type=Path)
    args = ap.parse_args()

    ev = args.evidence_dir.resolve()
    att_dir = ev / "attachments"
    doc_dir = ev / "documents"
    shot_dir = ev / "screenshots"
    for d in (att_dir, doc_dir, shot_dir):
        d.mkdir(parents=True, exist_ok=True)

    journal = Journal(args.journal)
    findings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900}, accept_downloads=True
        )
        page = ctx.new_page()

        # 1) 实际浏览目录页与分页
        page.goto(args.base_url, wait_until="domcontentloaded")
        page.screenshot(path=str(shot_dir / "index-p1.png"), full_page=True)
        count_text = page.get_by_test_id("count").inner_text()
        page_ids = []
        page_no = 1
        while True:
            rows = page.locator('tr[data-record-id]')
            n = rows.count()
            for i in range(n):
                page_ids.append(rows.nth(i).get_attribute("data-record-id"))
            next_link = page.get_by_role(
                "navigation", name="资料分页"
            ).get_by_role("link", name=f"第{page_no + 1}页", exact=True)
            if next_link.count() == 0:
                break
            page_no += 1
            next_link.click()
            page.wait_for_load_state("domcontentloaded")
        page.screenshot(path=str(shot_dir / "index-last.png"), full_page=True)

        # 2) 逐条打开详情页，下载附件与文书/扫描副本
        for rid in page_ids:
            page.goto(f"{args.base_url}/record/{rid}", wait_until="domcontentloaded")
            page.screenshot(
                path=str(shot_dir / f"record-{rid}.png"), full_page=True
            )
            shown_id = page.get_by_test_id("record-id").inner_text()
            shown_digest = page.get_by_test_id("digest").inner_text()
            shown_ref = page.get_by_test_id("reference").inner_text()
            fields_text = page.get_by_test_id("fields").inner_text()
            assert shown_id == rid
            assert shown_ref == f"{rid}@{shown_digest}"

            with page.expect_download() as event:
                page.get_by_role("link", name="下载原始材料").click()
            att_path = att_dir / event.value.suggested_filename
            event.value.save_as(att_path)
            att_bytes = att_path.read_bytes()
            att_sha = digest(att_bytes)
            assert att_sha == shown_digest, f"{rid} 附件摘要与门户显示不一致"
            record = json.loads(att_bytes.decode("utf-8"))
            assert record["id"] == rid

            with page.expect_download() as event:
                page.get_by_role("link", name="下载文书或扫描副本").click()
            doc_path = doc_dir / event.value.suggested_filename
            event.value.save_as(doc_path)
            doc_sha = digest(doc_path.read_bytes())

            entry = {
                "id": rid,
                "category": record["category"],
                "title": record["title"],
                "revision": record["revision"],
                "reference": shown_ref,
                "record_sha256": att_sha,
                "attachment": str(att_path.relative_to(ev)),
                "document": str(doc_path.relative_to(ev)),
                "document_sha256": doc_sha,
                "fields": record["fields"],
            }
            findings.append(entry)
            journal.append(
                f"browse:{rid}",
                {
                    "observed_via": "chromium",
                    "record_url": f"{args.base_url}/record/{rid}",
                    "reference": shown_ref,
                    "attachment_sha256": att_sha,
                    "document_sha256": doc_sha,
                    "fields_reviewed": record["fields"],
                },
            )

        browser.close()

    summary = {
        "index_count_text": count_text,
        "browsed_pages": page_no,
        "record_ids_in_index_order": page_ids,
        "records": findings,
    }
    out = ev / "browse-results.json"
    out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"records": len(findings), "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
