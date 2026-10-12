# StoryWeaver Live Phase 3 検証実行記録簿 (Execution Log)

本ドキュメントは、Phase 3（アニメ調顔転生画像生成パイプライン）の各検証試行（Run）における **投入パラメータ、生成画像、Gate 判定結果、課題・所感** を時系列で記録し、完全なトレーサビリティを確保するための台帳です。

---

## 運用プロトコル（記録のルール）

1. **手順参照**: 実行手順および推奨パラメータは [phase3_revision_plan.md](file:///c:/antigravity/StoryWeaver/docs/plans/phase3_revision_plan.md) 第5章 を参照。
2. **記録のタイミング**: ComfyUI で Queue Prompt を実行し、画像を確認するごとに 1 レコード（Run）を追記。
3. **履歴の永続化**: 各 Run の記録完了後、直ちに Git コミットを作成。

---

## 検証実行ログ一覧

| Run ID | 実施日時 | 検証フェーズ | 主要変更点 | Gate 判定 | 結果サマリ |
| :--- | :--- | :---: | :--- | :---: | :--- |
| **RUN-3A-00** | 2026-10-11 | Phase 3-A (事前) | 添付JSON初期構成 (Base 20st, FD 0.45, 全身プロンプト) | ❌ NG | 構図分散、FD による別人化・首折れ懸念 |
| **RUN-3A-01** | *(次回実施)* | Phase 3-A | 構図固定、ip 0.72、FD denoise 0.26、7分許容 28st | *(判定待ち)* | 本人顔立ち固定と別人化防止の検証 |

---

## 各試行の詳細記録

---

### [RUN-3A-00] 初期ベースライン評価（添付 JSON 構成）

* **実施日**: 2026年10月11日
* **対象フェーズ**: Phase 3-A（現状分析）
* **ワークフロー ID**: `f18856ec-7f35-41b9-bc2f-69126996bcb1`
* **入力写真**: `reWIN_20260204_20_46_41_Pro.jpg`

#### 1. 設定パラメータ
* **プロンプト (Node 21)**:
  `masterpiece, best quality, very aesthetic, anime art style, 8k wallpaper, solo, confident smile, dynamic pose, full body, fantasy warrior, flowing cape, magical aura, glowing sword...` ＋ WD14 タグ
* **Base InstantID (Node 18)**: `ip_weight: 0.60`, `cn_strength: 0.25`, `end_at: 0.85`
* **KSampler (Node 2)**: `steps: 20`, `cfg: 6.0`, `euler_ancestral`, `karras`
* **FaceDetailer 用 InstantID (Node 25)**: `ip_weight: 0.60`, `cn_strength: 0.35`, `end_at: 1.0`
* **FaceDetailer (Node 20)**: `denoise: 0.45`, `bbox_crop_factor: 2.0`, `guide_size: 768`, `steps: 20`
* **WD14 Tagger (Node 19)**: `threshold: 0.40`

#### 2. Gate 3-A 判定結果
| 判定項目 | 基準 | 結果 | 備考・課題 |
| :--- | :--- | :---: | :--- |
| **本人同一性** | 目鼻立ち・髪型・眼鏡の一致 | ❌ 不足 | `dynamic pose, full body` により顔の描画解像度が不足。`ip_weight: 0.60` では Animagine のアニメバイアスに負けて標準顔に埋没。 |
| **美麗アニメ品質** | セル画調、瞳のハイライト | ◯ 良好 | Animagine XL FP8 による塗りは高品質。 |
| **`solo` 遵守** | 1名のみ、分裂なし | ◯ 達成 | コラージュや多人数化は発生せず。 |
| **別人化の非発生** | FD 適用後も同一人物 | ❌ 破綻 | `denoise: 0.45` により Base の顔立ちが別人に上書き。クロップ画像への `cn_strength: 0.35` 適用で首の角度不整合リスクあり。 |

#### 3. 課題と次回 (RUN-3A-01) への改善指示
1. プロンプトをポートレート（バストアップ、顔中心）に固定し、顔の描画面積を最大化。
2. Base InstantID の `ip_weight` を `0.72`、`end_at: 1.0` に引き上げて本人顔貌を固定。
3. 時間7分許容を活用し、KSampler を `28 steps`, `cfg: 6.5` に向上。
4. FaceDetailer の `denoise` を `0.26`、`crop_factor` を `1.4` に適正化し、Node 25 の `cn_strength` を `0.0` に解除。

---

### [RUN-3A-01] Phase 3-A 第1回改善検証（本人同一性確立トライ）

* **実施日**: *(実施後に記入)*
* **対象フェーズ**: Phase 3-A (本人同一性とアニメ品質の確立)
* **適用手順**: [phase3_revision_plan.md](file:///c:/antigravity/StoryWeaver/docs/plans/phase3_revision_plan.md) 第5章 Step 1〜6 を適用

#### 1. 設定パラメータ
* **プロンプト (Node 21)**:
  `masterpiece, best quality, very aesthetic, anime art style, solo, portrait, close-up face, upper body, looking at viewer, detailed facial features, sharp focus, simple background` ＋ WD14 タグ
* **Base InstantID (Node 18)**: `ip_weight: 0.72`, `cn_strength: 0.25`, `end_at: 1.0`
* **KSampler (Node 2)**: `steps: 28`, `cfg: 6.5`, `euler_ancestral`, `karras`
* **FaceDetailer 用 InstantID (Node 25)**: `ip_weight: 0.45`, `cn_strength: 0.0`, `end_at: 0.70`
* **FaceDetailer (Node 20)**: `denoise: 0.26`, `bbox_crop_factor: 1.4`, `feather: 10`, `steps: 20`
* **WD14 Tagger (Node 19)**: `threshold: 0.30`

#### 2. 生成結果・出力
* **Base プレビュー (Node 26)**: *(確認結果を記入)*
* **完成画像 (Node 9 / test-anime)**: *(保存ファイル名を記入)*
* **所要時間**: *(秒/分を記入)*

#### 3. 🚧 Gate 3-A 判定
| 判定項目 | 合格基準 | 合否 | 観察結果・メモ |
| :--- | :--- | :---: | :--- |
| **A-1 本人同一性** | 目元の特徴、髪型、眼鏡が元写真と一致しているか | ☐ | *(記入欄)* |
| **A-2 美麗アニメ品質** | 実写臭さのない美麗なセル画塗り・瞳のハイライト | ☐ | *(記入欄)* |
| **A-3 `solo` 遵守** | 厳密に1名のみ描画され、分裂がないか | ☐ | *(記入欄)* |
| **A-4 別人化の非発生** | FD 適用後も Base の本人の顔貌が壊れていないか | ☐ | *(記入欄)* |

#### 4. 総合評価・気づき
* *(実施後の所感を記入)*
