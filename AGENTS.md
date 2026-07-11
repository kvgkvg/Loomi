# Organizational AI Memory — Hackathon Project (Track P5)

## Bài toán
Tri thức AI (prompt, workflow, agent config) của nhân viên bị mất khi họ đổi vai trò/nghỉ việc. Xây capability layer để phát hiện, tái sử dụng tri thức đó xuyên phòng ban.

## Pipeline tổng thể

```
Nguồn (Git/IDE, Chat logs, Workflow tools)
  → Adapter (dịch về canonical event)
  → Capture pipeline (diff & version → rationale LLM → embedding)
  → Memory store (Postgres/SQLite + Chroma vector)
  → Recommend engine / Onboarding assistant
  → Delivery UI (Streamlit)
```

## Pipeline chi tiết từng component

**1. Adapter** (mỗi nguồn 1 adapter riêng)
```
Sự kiện thô (commit / chat export / workflow JSON)
  → Đọc raw signal đặc thù công cụ
  → Dịch về canonical event {title, content, source_tool, raw_signal}
  → Ghi vào bảng raw_events (processed = false)
```

**2. Capture pipeline** (chạy tuần tự, mỗi bước phụ thuộc bước trước)
```
raw_events (processed = false)
  → Diff & version: so bản mới/cũ → ghi assets + asset_versions
  → Rationale extraction (LLM): đọc content + raw_signal
      → trả JSON {problem, failed_attempts, constraints, confidence}
      → ghi bảng rationale
  → Embedding: embed content + rationale.problem → ghi vào Chroma
  → Đánh dấu raw_events.processed = true
  (nếu bước nào lỗi: giữ processed = false, không raise exception, để retry)
```

**3. Recommend engine**
```
task_description (string)
  → Embed bằng đúng model đã dùng ở bước Embedding
  → Vector search top-k trong Chroma
  → Join Postgres lấy metadata (owner, usage_count, rationale)
  → Rerank theo confidence + usage_count
  → Trả về list [{asset_id, title, problem, score, usage_count, owner_name}]
```

**4. Onboarding assistant**
```
asset_id (+ optional question)
  → Lấy asset + toàn bộ asset_versions + rationale qua các version
  → LLM tổng hợp: vấn đề gốc, ràng buộc, edge case
  → Nếu có question: trả lời grounded trên rationale đã lưu
  → Trả về {explanation, cited_versions, cited_constraints}
```

**5. Delivery UI**
```
Input người dùng (task description hoặc câu hỏi)
  → Gọi song song recommend() và/hoặc explain_asset()
  → Render kết quả trong 1 màn hình chat (Streamlit/Gradio)
```

## Stack
- DB: Postgres (hoặc SQLite) qua `db/client.py`
- Vector: Chroma
- LLM: Claude API (rationale extraction, onboarding explanation)
- Embedding: `sentence-transformers/all-MiniLM-L6-v2` — **không đổi model giữa các module**
- UI: Streamlit/Gradio

## Cấu trúc thư mục
```
db/                     # Khang — client.py, seed script
adapters/               # Ấn — git_adapter.py
capture_pipeline/       # Ấn — process.py
recommend/              # Hồng — engine.py
onboarding/             # Trí — assistant.py
delivery/               # Trí — app.py (Streamlit)
memory/                 # Log tiến độ, quyết định, lỗi đã gặp — xem quy tắc bên dưới
```

## Bảng DB chính
`raw_events`, `assets`, `asset_versions`, `rationale`, `users`, `asset_usage`, `tags`, `asset_tags`. (`rationale_evidence`, `asset_relations` không bắt buộc cho MVP.)

## Quy tắc ghi memory (bắt buộc)
Sau mỗi phiên làm việc (hoặc mỗi lần hoàn thành 1 task con), ghi lại vào `memory/<tên>.md`:
- Đã làm gì, quyết định kỹ thuật nào đã chọn và vì sao
- Lỗi đã gặp và cách đã sửa (để người khác/agent sau không lặp lại)
- Việc còn dang dở, bước tiếp theo cần làm

Không ghi đè memory cũ — luôn append. Đầu mỗi session mới, đọc lại `memory/` trước khi bắt đầu code.

## Skill bắt buộc dùng
- **superpowers** — dùng cho các pattern/kỹ thuật engineering chung khi code từng component.
- **caveman** — dùng khi cần Claude trả lời/tóm tắt ngắn gọn, tiết kiệm token trong lúc debug nhanh.
- **ponytail** — dùng khi cần Claude ưu tiên giải pháp đơn giản, ít over-engineer, đúng tinh thần MVP hackathon.

## Quy ước code
- Mọi function core đều là pure input → output theo đúng contract trong `work-assignment.md` — không tự đổi signature khi chưa báo team.
- Không tự kết nối DB riêng — luôn import qua `db/client.py`.
- Lỗi LLM call: không raise exception làm chết pipeline, ghi `raw_events.processed = false` để retry.
- Kịch bản demo trung tâm: 1 người tạo tri thức (Git commit) → 1 người khác chưa từng biết, được hệ thống chủ động gợi ý lại.

## Không làm (out of scope cho hackathon)
- Không dùng graph DB (Neo4j) — quan hệ giữa asset dùng bảng nối đơn giản trong Postgres.
- Không build governance/RBAC đầy đủ — chỉ version history + attribution đơn giản.
- Không cần hỗ trợ multi-branch/multi-environment cho asset.
