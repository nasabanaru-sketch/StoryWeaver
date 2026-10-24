# AGENTS.md - StoryWeaver プロジェクト基本方針・共通制約

本ドキュメントは、**StoryWeaver Live** プロジェクトにおいて AI エージェントおよび開発者が遵守すべき共通原則、システムアーキテクチャ、制約事項を定めたものです。

---

## 1. プロジェクト概要

- **名称**: StoryWeaver Live
- **目的**: 展示ブース等のイベント現場において、来場者の顔写真（Webカメラ）と発話音声（マイク）からリアルタイムにアニメ調のキャラクターイラストとセリフ・朗読音声を同時生成する完全ローカル稼働型AIインスタレーション。
- **ターゲット環境**: ThinkPad X1 Extreme (GPU: RTX 3080 Laptop 16GB / RAM: 32GB / Windows / WSL2 or PowerShell)
- **コア原則**: **完全ローカル稼働（外部API非依存）** & **展示本番中のゼロダウンタイム・OOMゼロ**

---

## 2. システム構成 & アーキテクチャ

| コンポーネント | ポート / パス | 役割 | 主要モデル・技術 |
| :--- | :--- | :--- | :--- |
| **フロントエンド UI** | `8000` or Static | カメラ撮影、音声録音、カード表示、音声朗読 | Vanilla HTML/CSS/JS (Web Speech API) |
| **オーケストレーター** | `http://localhost:8000` | パイプライン制御、API集約、ファイル受け渡し | FastAPI, Uvicorn, Python Multipart |
| **音声認識 (ASR)** | In-process / FastAPI | 発話の日本語テキスト化・感情解析 | `FunAudioLLM/SenseVoiceSmall` |
| **小型 LLM** | `http://localhost:11434` | 感情解釈、アニメ演出タグ合成、日本語朗読文生成 | Ollama (`gemma4:e2b` / `qwen2.5:3b`) |
| **画像生成エンジン** | `http://localhost:8188` | アニメ調SDXL + InstantID による高速顔転生画像生成 | ComfyUI, `Animagine XL v3.1 FP8`, `SDXL Lightning 4-step` |

---

## 3. 最重要制約事項 (Critical Constraints)

### ① VRAM 16GB 厳守（OOM防止）
- 合計 VRAM 使用量を **14.5 GB 以内** に抑え、最低 1.5 GB の動的バッファ・熱ダウングレード耐性を確保すること。
- メモリ配分目安:
  - OS / ディスプレイ: ~1.5 GB
  - ComfyUI (Animagine FP8 + InstantID + ControlNet): ~10.5 GB
  - Ollama (Gemma 4 e2b / Qwen 2.5 3B): ~2.2 GB
  - SenseVoice: ~0.4 GB (CPUまたはRAMへ逃がす設定も可)
- モデルの多重ロードや同時実行による VRAM スパイクを禁止する。

### ② 生成時間とタイムアウト設計（画質最優先・最大7分許容）
- **時間制約の緩和（2026-10-11 改訂）**:
  - 短い生成時間による制約（ステップ削減・低品質LoRAによる描写崩れ）を排除するため、**画質と本人同一性の許容水準が確立するまでは、生成時間を一旦最大7分（420秒）まで許容** する。
  - 画質の許容範囲を確定させた後、後工程（Phase 3-C）にて時間を短縮していくアプローチをとる。
- **ブロッキング防止とタイムアウト設定**:
  - ComfyUI のポーリングや Ollama のレスポンス待機で無限ループを作らないこと。
  - ComfyUI の待機タイムアウトは最大 500秒（約8分20秒）程度に設定し、長時間のサンプリングや高精細FaceDetailer処理を打ち切らない設計とすること。
  - Ollama 単体の通信には引き続き最大30秒のタイムアウトを設定すること。

### ③ 冪等性と一時ファイルクリーンアップ
- 体験者ごとの顔画像や音声ファイルは、処理完了後またはエラー時にリークせず適切に上書き・破棄すること。

---

## 4. プロジェクトディレクトリ規約

```text
StoryWeaver/
├── AGENTS.md                  # 本ファイル（基本方針・共通制約）
├── Attached_doc/              # プロジェクト仕様書・構築マニュアル
├── .agents/                   # エージェント用コンフィグ・ナレッジ
│   ├── rules/                 # 【制約】エラー再発防止・コーディング規約（自動適用）
│   │   ├── error-prevention.md
│   │   └── database-rules.md
│   ├── workflows/             # 【手順】反復タスクの定型手順（スラッシュコマンド実行）
│   │   ├── postmortem.md
│   │   └── run-migration.md
│   └── skills/                # 【専門ナレッジ】特定の文脈でのみ自動ロードする手順群
│       └── incident-check/
│           └── SKILL.md
└── docs/                      # 【記録】人間と共有する設計・計画のアーカイブ
    ├── plans/                 # 実装計画書（Implementation Plan）の保存先
    └── postmortems/           # 発生した重大エラーの経緯・根本原因ログ
```

---

## 5. エージェント開発・作業ルール

1. **仕様ドキュメントの尊重**:
   - `Attached_doc/storyweaver_live.md` に記載されたプロンプト形式（Animagine 品質タグ、InstantID 重み `0.55〜0.60`、Lightning 4-step）を変更する場合は根拠を提示すること。
2. **変更前の安全性検証**:
   - バックエンドおよび ComfyUI 連携スクリプトの修正時は、接続エラー・タイムアウト・レスポンスフォーマットのバリデーションを必須とすること。
3. **障害記録の徹底**:
   - 重大な不具合や VRAM 不足によるクラッシュが発生した場合は、`.agents/workflows/postmortem.md` に従い `docs/postmortems/` へログを残し、再発防止ルールを `.agents/rules/` に追記すること。
4. **機能更新時のマニュアル追従（必須）**:
   - API、設定項目、画面UI、分析モード等の機能追加・改修を行った場合は、必ず `docs/OPERATION_MANUAL.md`（操作・運用マニュアル）に手順・設定説明を追記・更新すること。
