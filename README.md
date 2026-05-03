# Mini Novel Webtool (Vercel-ready)

Tool Python nhỏ gọn để crawl nội dung truyện ngôn tình từ URL và xuất file TXT.

## Deploy lên Vercel

- Repo này đã có `vercel.json` để map toàn bộ route vào Flask app.
- Dùng `requirements.txt` tương thích serverless, **không cần Playwright/Chromium**.
- Output được lưu tạm vào `/tmp/novel_output` khi chạy trên Vercel.

## Chạy local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Mở `http://127.0.0.1:5000`.

## Luồng sử dụng

1. Nhập URL trang truyện.
2. Tool phân tích title + chapter list.
3. Xác nhận title, chapter bắt đầu/kết thúc.
4. Crawl và lọc text rác.
5. Tải TXT về.

## Lưu ý thực tế trên Vercel

- Serverless có timeout, nên crawl theo từng đoạn chapter vừa phải (ví dụ 50-150 chương/lần).
- Site JS/CAPTCHA mạnh vẫn có thể fail; tool sẽ trả lỗi tiếng Việt để user biết bước nào thất bại.


## Khắc phục lỗi 403 (Vercel IP bị chặn)

- Một số site chặn datacenter IP nên sẽ báo `403 Forbidden` dù chạy local bình thường.
- Tool đã tự retry theo thứ tự: URL gốc -> HTTPS version của URL -> proxy qua ScraperAPI (nếu có key).
- Trên Vercel, thêm Environment Variable: `SCRAPERAPI_KEY=<your_key>`.
