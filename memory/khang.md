# Memory — Khang (DB setup)

## Session 2026-07-11

### Đã làm
- Tạo conda env `loomi` (python 3.11), cài `chromadb`. Activate: `conda activate loomi`.
- `db/schema.sql` — đủ 9 bảng theo DDL trong task.md §3, dialect SQLite.
- `db/client.py` — `get_pg_connection()` (sqlite3, row_factory=Row, FK on, auto-apply schema idempotent) + `get_vector_collection()` (Chroma PersistentClient, collection `assets`, cosine).
- `db/seed.py` — 6 assets (có asset 2 version), 4 users, rationale đầy đủ, tags, asset_usage, và vector trong Chroma. Chạy: `python -m db.seed` từ repo root. Idempotent (xoá seed cũ trước khi insert).
- `.env` — LOOMI_DB_PATH=db/loomi.db, LOOMI_CHROMA_PATH=db/chroma.
- `.gitignore` — bỏ qua db file, chroma dir, .env.

### Quyết định kỹ thuật
- **SQLite thay vì Postgres** — task.md cho phép, không cần server, cả team clone repo là chạy được ngay. `get_pg_connection()` giữ nguyên tên theo contract dù trả sqlite3.Connection.
- **UUID lưu TEXT, JSONB lưu TEXT (JSON string)** — SQLite không có kiểu native. Đọc `rationale.failed_attempts`/`constraints` nhớ `json.loads()`.
- **Embedding: dùng embedding mặc định của Chroma** = all-MiniLM-L6-v2 (bản ONNX) — đúng model team đã chốt. Ấn/Hồng chỉ cần `collection.add(documents=...)` / `collection.query(query_texts=...)`, KHÔNG tự embed bằng model khác.
- **Chroma document recipe**: `title + \n + content + \n + rationale.problem`, id = asset_id, metadata {title, type, owner}. Ấn nên dùng đúng recipe này trong capture pipeline.

### Lỗi đã gặp
- Ban đầu setup bằng `uv venv` — đổi sang conda env `loomi` theo yêu cầu.
- Máy in warning `OpenSSL 3's legacy provider failed to load` khi chạy conda — vô hại, bỏ qua.

### Verify đã chạy (bằng chứng)
- `python -m db.seed` → "Seeded 6 assets, 4 users, 6 vectors in Chroma."
- Counts: users 4, assets 6, asset_versions 7, rationale 7, asset_usage 3, tags 16, asset_tags 18. 10 bảng đều tạo được (task.md ghi "9 tables" nhưng DDL liệt kê 10 — schema theo DDL).
- Semantic search test: query "I need to build an agent that classifies sales leads" (khác hẳn wording gốc) → top-1 "Lead qualification agent for inbound sales" distance 0.344. Match theo nghĩa OK.
- Lần chạy Chroma đầu tiên tự tải model ONNX all-MiniLM-L6-v2 (~79MB) về `~/.cache/chroma/` — chỉ chậm 1 lần đầu.

### Còn dang dở / bước tiếp theo
- Task Khang XONG. Team chạy: `conda activate loomi`, rồi `python -m db.seed` (nếu muốn reset data), import `from db.client import get_pg_connection, get_vector_collection`.
- Nếu ai dùng env khác: chỉ cần `pip install chromadb`.

## Session 2026-07-11 - Phase 2 (Storage Compatibility)

### Đã làm
- Cài đặt `psycopg[binary]` vào virtual environment `.venv` và lưu vào `requirements.txt`.
- Tạo schema PostgreSQL `db/schema_pg.sql` sử dụng các kiểu dữ liệu native: `UUID`, `JSONB`, `BOOLEAN`, và `TIMESTAMPTZ`.
- Thêm bảng `git_poll_state` vào cả schema SQLite (`db/schema.sql`) và schema PostgreSQL (`db/schema_pg.sql`).
- Cập nhật `db/client.py` để hỗ trợ kết nối PostgreSQL nếu tìm thấy biến môi trường `DATABASE_URL`.
- Cập nhật `db/client.py` để hỗ trợ kết nối Chroma từ xa nếu có biến môi trường `CHROMA_HOST`.
- Viết bộ test kiểm thử hợp đồng (contract tests) `tests/db/test_pg_compat.py` để xác minh tính tương thích của cả 2 database backend SQLite và PostgreSQL.
- Chạy toàn bộ test suite (`uv run pytest`), tất cả 38 test đã pass thành công.

### Quyết định kỹ thuật
- **Tương thích kiểu dữ liệu**: Postgres native trả về kiểu `uuid.UUID` và `dict`/`list` cho cột `JSONB`. Để tránh phá vỡ code xử lý cũ vốn giả định kiểu `TEXT` từ SQLite, class `CompatibleRow` sẽ tự động chuyển đổi các kiểu UUID về dạng `str`, JSONB về chuỗi JSON string, và Decimal về `float`.
- **Tương thích Placeholder**: Viết Wrapper cho Connection và Cursor của PostgreSQL để tự động dịch các placeholder `?` của SQLite thành `%s` của PostgreSQL. Đồng thời tự động dịch các giá trị boolean dạng số (0/1) trong các câu lệnh SQL insert/update thành `FALSE/TRUE` tương thích với kiểu `BOOLEAN` nghiêm ngặt của Postgres.
- **Remote Chroma**: Hỗ trợ remote Chroma bằng cách kiểm tra `CHROMA_HOST` và kết nối qua `chromadb.HttpClient`.

### Verify đã chạy (bằng chứng)
- Chạy `uv run pytest` kết quả: `38 passed, 1 skipped in 2.26s`.
- Cả hai test case parameterized cho `sqlite` và `postgres` trong `tests/db/test_pg_compat.py` đều pass thành công trên database PostgreSQL `loomi_test` cục bộ.

