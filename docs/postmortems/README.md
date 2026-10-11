# 重大障害・ポストモーテム記録 (docs/postmortems/)

本ディレクトリは、展示本番や開発テスト環境で発生した重大障害・エラー（CUDA OOM、通信途絶、生成ハング等）の経緯、タイムライン、根本原因（RCA）、および再発防止策を恒久的にアーカイブする場所です。

---

## 運用ルール
1. 障害発生時は、ワークフロー [postmortem.md](file:///c:/antigravity/StoryWeaver/.agents/workflows/postmortem.md) に従って調査を実施します。
2. 調査完了後、本ディレクトリに記録書を作成します。
3. 導き出された再発防止策は [error-prevention.md](file:///c:/antigravity/StoryWeaver/.agents/rules/error-prevention.md) 等のルールへ即時追記します。

## 命名規則
- `YYYY-MM-DD_<incident_name>.md`
- 例: `2026-10-03_comfyui_vram_oom.md`

## 記録書テンプレート
[postmortem.md](file:///c:/antigravity/StoryWeaver/.agents/workflows/postmortem.md) を参照してください。
