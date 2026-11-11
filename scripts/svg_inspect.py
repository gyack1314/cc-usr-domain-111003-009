"""在浏览器中渲染已通过门户下载的 SVG 扫描副本并截图，提取页面文字作为版次/叶序证据。

门户 /document/ 以 Content-Disposition: attachment 提供文件，浏览器导航会触发下载，
因此这里使用遍历阶段实际下载的 SVG 副本，包装为本地 data: URL 后在 Chromium 中渲染查看。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/workspace")

from playwright.sync_api import sync_playwright  # noqa: E402

from workbench.evidence import Journal, digest  # noqa: E402


def main():
    doc_dir = Path("/workspace/evidence/downloads/documents")
    out_dir = Path("/workspace/evidence/svg_views")
    out_dir.mkdir(parents=True, exist_ok=True)
    journal = Journal("/workspace/state/journal/worklog.sqlite3")
    ids = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]
    browse = json.loads(
        Path("/workspace/evidence/downloads/browse-results.json").read_text(
            encoding="utf-8"
        )
    )
    doc_sha = {r["id"]: r["document_sha256"] for r in browse["records"]}
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 960, "height": 1320})
        for rid in ids:
            svg_path = doc_dir / f"{rid}.svg"
            raw = svg_path.read_bytes()
            raw_sha = digest(raw)
            assert raw_sha == doc_sha[rid], f"{rid} 渲染文件与下载摘要不一致"
            svg_text = raw.decode("utf-8")
            page.set_content(
                "<!doctype html><meta charset='utf-8'>"
                "<body style='margin:0'>" + svg_text,
                wait_until="load",
            )
            page.locator("svg").screenshot(path=str(out_dir / f"{rid}.png"))
            texts = [
                loc.text_content()
                for loc in page.locator("svg text").all()
            ]
            results.append(
                {
                    "id": rid,
                    "source_download": str(svg_path),
                    "source_sha256": raw_sha,
                    "svg_texts": texts,
                }
            )
            journal.append(
                f"svgview2:{rid}",
                {
                    "observed_via": "chromium-rendered-download",
                    "source_sha256": raw_sha,
                    "svg_texts": texts,
                    "screenshot": str(out_dir / f"{rid}.png"),
                },
            )
        browser.close()
    (out_dir / "svg-views.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"rendered": len(results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
