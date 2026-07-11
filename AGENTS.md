# Organizational AI Memory — Hackathon Project (Track P5)

## Bài toán
Tri thức AI (prompt, workflow, agent config) của nhân viên bị mất khi họ đổi vai trò/nghỉ việc. Xây capability layer để phát hiện, tái sử dụng tri thức đó xuyên phòng ban.

## Kiến trúc
```
Nguồn (Git/IDE, Chat logs, Workflow tools)
  → Adapter (dịch về canonical event)
  → Capture pipeline (diff & version → rationale LLM → embedding)
  → Memory store (Postgres/SQLite + Chroma vector)
  → Recommend engine / Onboarding assistant
  → Delivery UI (Streamlit)
```

## Stack
- DB: Postgres (hoặc SQLite) qua `db/client.py`
- Vector: Chroma
- LLM: Claude API (rationale extraction, onboarding explanation)
- Embedding: `sentence-transformers/all-MiniLM-L6-v2` — **không đổi model giữa các module**, vì vector phải so sánh được với nhau
- UI: Streamlit/Gradio

## Cấu trúc thư mục
```
db/adapters.py        # Người A — client.py, seed script
adapters/              # Người B — git_adapter.py
capture_pipeline/      # Người B — process.py
recommend/             # Người C — engine.py
onboarding/             # Người D — assistant.py
delivery/               # Người D — app.py (Streamlit)
```

## Bảng DB chính
`raw_events`, `assets`, `asset_versions`, `rationale`, `users`, `asset_usage`, `tags`, `asset_tags`. (`rationale_evidence`, `asset_relations` không bắt buộc cho MVP.)

## Quy ước code
- Mọi function core đều là pure input → output theo đúng contract đã định nghĩa trong `phan-chia-cong-viec.md` — không tự đổi signature khi chưa báo team.
- Không tự kết nối DB riêng — luôn import qua `db/client.py`.
- Lỗi LLM call: không raise exception làm chết pipeline, ghi `raw_events.processed = false` để retry.
- Kịch bản demo trung tâm: 1 người tạo tri thức (Git commit) → 1 người khác chưa từng biết, được hệ thống chủ động gợi ý lại.

## Không làm (out of scope cho hackathon)
- Không dùng graph DB (Neo4j) — quan hệ giữa asset dùng bảng nối đơn giản trong Postgres.
- Không build governance/RBAC đầy đủ — chỉ version history + attribution đơn giản.
- Không cần hỗ trợ multi-branch/multi-environment cho asset.
