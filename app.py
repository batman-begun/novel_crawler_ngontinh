import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin

import cloudscraper
from bs4 import BeautifulSoup
from flask import Flask, render_template_string, request, send_file

app = Flask(__name__)
OUTPUT_DIR = Path("/tmp/novel_output") if os.getenv("VERCEL") else Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Mini Novel Webtool</title>
<style>body{font-family:Arial,sans-serif;max-width:900px;margin:24px auto;line-height:1.5}input,button{padding:8px;margin:6px 0;width:100%}.card{border:1px solid #ddd;border-radius:10px;padding:16px;margin-bottom:16px}.ok{color:#0a7d2e}.err{color:#c62828;white-space:pre-wrap}code{background:#f2f2f2;padding:2px 4px;border-radius:4px}</style></head><body>
<h1>Mini Novel Webtool (Ngôn Tình)</h1>
<div class="card"><form method="post" action="/analyze"><label>URL mục tiêu:</label><input name="url" required placeholder="https://..."><button type="submit">1) Phân tích truyện</button></form></div>
{% if analysis %}<div class="card"><h3>2) Xác nhận thông tin</h3><p><b>Tên truyện (detect):</b> {{ analysis.title }}</p><p><b>Số chương detect:</b> {{ analysis.chapter_count }}</p><p><b>Chương đầu detect:</b> <code>{{ analysis.first_chapter }}</code></p>
<form method="post" action="/crawl"><input type="hidden" name="first_chapter_url" value="{{ analysis.first_chapter_url }}"><label>Xác nhận tên truyện:</label><input name="confirmed_title" value="{{ analysis.title }}" required><label>Start chapter:</label><input name="start" type="number" min="1" value="1" required><label>End chapter:</label><input name="end" type="number" min="1" value="{{ analysis.chapter_count }}" required><button type="submit">3) Bắt đầu crawl</button></form></div>{% endif %}
{% if result %}<div class="card">{% if result.ok %}<p class="ok"><b>Hoàn tất:</b> {{ result.message }}</p><a href="/download/{{ result.filename }}">Tải file TXT</a>{% else %}<p class="err"><b>Lỗi:</b> {{ result.message }}</p>{% endif %}</div>{% endif %}
</body></html>"""


@dataclass
class AnalysisResult:
    title: str
    chapter_count: int
    first_chapter: str
    first_chapter_url: str


def client():
    return cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})


def get_soup(url: str) -> BeautifulSoup:
    r = client().get(url, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return BeautifulSoup(r.text, "lxml")


def clean_title(name: str) -> str:
    return re.sub(r"[^\w\-\s一-龥]", "", name, flags=re.UNICODE).strip() or "novel"


def extract_text(soup: BeautifulSoup) -> str:
    stop_keywords = ["上一章", "下一章", "返回目录", "推荐", "广告", "收藏", "书签", "目录", "作者", "版权"]
    lines = []
    for node in soup.find_all(["p", "div", "span"]):
        text = " ".join(node.stripped_strings).strip()
        if not text or any(k in text for k in stop_keywords):
            continue
        if len(re.findall(r"[\u4e00-\u9fff]", text)) >= 20:
            lines.append(text)
    seen = set()
    uniq = [x for x in lines if not (x in seen or seen.add(x))]
    return "\n\n".join(uniq)


def analyze_novel(url: str) -> AnalysisResult:
    soup = get_soup(url)
    title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled"
    chapter_links: List[Tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        txt = a.get_text(strip=True)
        if re.search(r"(第\s*\d+\s*[章节回])", txt):
            chapter_links.append((txt, urljoin(url, a["href"])))
    if not chapter_links:
        start = soup.find("a", string=lambda x: x and ("开始阅读" in x or "阅读" in x))
        if start:
            chapter_links = [("Chương 1", urljoin(url, start["href"]))]
    if not chapter_links:
        raise RuntimeError("Không detect được chapter list. Website có thể dùng JS/CAPTCHA mạnh vượt ngoài khả năng serverless.")
    return AnalysisResult(title, len(chapter_links), chapter_links[0][0], chapter_links[0][1])


def crawl_novel(start_url: str, title: str, start_idx: int, end_idx: int) -> Path:
    out = OUTPUT_DIR / f"{clean_title(title)}_{start_idx}_{end_idx}.txt"
    visited, url, idx = set(), start_url, 1
    with out.open("w", encoding="utf-8") as f:
        while url and url not in visited and idx <= end_idx:
            visited.add(url)
            soup = get_soup(url)
            if idx >= start_idx:
                header = soup.find(["h1", "h2", "h3"])
                chap_title = header.get_text(strip=True) if header else f"Chapter {idx}"
                content = extract_text(soup)
                if not content:
                    raise RuntimeError(f"Không lấy được nội dung chương {idx}.")
                f.write(f"\n\n===== {chap_title} =====\n\n{content}")
            nxt = soup.find("a", string=lambda x: x and ("下一章" in x or "下页" in x or "下一页" in x))
            if not nxt or "href" not in nxt.attrs:
                break
            url = urljoin(url, nxt["href"])
            idx += 1
            time.sleep(0.2)
    return out


@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML)


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        result = analyze_novel(request.form.get("url", "").strip())
        return render_template_string(HTML, analysis=result)
    except Exception as e:
        return render_template_string(HTML, result={"ok": False, "message": f"Phân tích thất bại: {e}"})


@app.route("/crawl", methods=["POST"])
def crawl():
    try:
        title = request.form["confirmed_title"].strip()
        start, end = int(request.form["start"]), int(request.form["end"])
        if start < 1 or end < start:
            return render_template_string(HTML, result={"ok": False, "message": "Start/End chapter không hợp lệ."})
        out = crawl_novel(request.form["first_chapter_url"].strip(), title, start, end)
        return render_template_string(HTML, result={"ok": True, "message": f"Đã crawl xong chapter {start} -> {end}.", "filename": out.name})
    except Exception as e:
        return render_template_string(HTML, result={"ok": False, "message": f"Crawl thất bại: {e}"})


@app.route("/download/<name>")
def download(name: str):
    p = OUTPUT_DIR / name
    if not p.exists():
        return render_template_string(HTML, result={"ok": False, "message": "Không tìm thấy file để tải."})
    return send_file(p, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
