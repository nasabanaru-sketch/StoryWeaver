# StoryWeaver Live — VLM 外見抽出（短髪・坊主頭判定）修正仕様書

## 1. 背景と解決すべき課題

Phase 2 の画像生成評価において、以下の課題が確認されたため `verify_step1_vlm.py` の改修を行う。

1. **VLM（`gemma4:e2b`）による `short hair` への誤分類**:
   - 現行の `verify_step1_vlm.py` では、Pydantic スキーマ（`FaceVlmExtraction`）および `SYSTEM_PROMPT` に髪の長さ（`buzz cut` / `very short hair` / `short hair`）の客観的な境界基準が定義されていない。
   - その結果、`koji-bose.jpg`（坊主〜ベリーショートの男性）が安全側の `short hair` と判定され、Animagine XL 3.1 で生成した際に頭頂部のアホ毛や耳周りの毛束を持つ「標準的なアニメのショートヘア」になってしまう。
2. **過度なタグ重み付けによる画質・構図破綻の防止**:
   - ComfyUI 上で単純に `buzz cut` を強く効かせすぎたり、ネガティブプロンプトに強い重み（`1.3` など）を多数追加すると、Animagine XL 3.1 の学習バイアスにより画像全体がボケて剣などの構図が破綻する現象が確認された。
   - そのため、Positive 側は `buzz cut` と `very short hair` の併記でシルエットを固定しつつ、Negative 側はアホ毛・耳かかり・ボブ化を適度な重み（`1.2` 以下）で抑止する構成とする。
3. **不適切なフォールバックルールの排除（重要）**:
   - 「`1boy` かつ `exposed_forehead == True` の `short hair` を無条件で `buzz cut` に強制変換する」といったルールベース変換は**絶対に実装しないこと**（額を出した一般的な短髪男性まで全員坊主頭になる副作用を防ぐため）。
   - 分類精度そのものを「JSON Schema の `description` 厳格化」と「`SYSTEM_PROMPT` の基準明記」によって改善する。

---

## 2. `verify_step1_vlm.py` の修正内容

対象ファイル: `verify_step1_vlm.py`

### 2.1 `FaceVlmExtraction`（Pydantic JSON Schema 定義）の修正

`hair_length` および `has_bangs` の `Field(description=...)` を以下のように更新し、ミリ・センチ単位および頭皮・耳の露出基準をスキーマレベルで明記する。

```python
class FaceVlmExtraction(BaseModel):
    face_detected: bool = Field(
        ...,
        description=(
            "Set to true if a human face is clearly visible and recognizable. "
            "Set to false if no face is present, or the face is covered/obscured by hands, mask, or extreme blur."
        ),
    )
    gender_tag: Literal["1boy", "1girl"] = Field(
        ...,
        description="Gender tag for Danbooru/Animagine: '1boy' or '1girl'. If face_detected is false, default to '1boy'.",
    )
    hair_length: Literal[
        "buzz cut", "very short hair", "short hair", "medium hair", "long hair", "bald"
    ] = Field(
        ...,
        description=(
            "Strict hair length classification based on physical appearance: "
            "'bald' = no hair on scalp; "
            "'buzz cut' = shaved or clipped extremely close to the scalp (under 1 cm), head contour/scalp is visible, no bangs or locks; "
            "'very short hair' = cropped short (1 to 3 cm, crew cut), ears and forehead are completely uncovered, no hanging strands; "
            "'short hair' = 4 to 15 cm, hair has visible locks/strands, covers part of forehead (bangs) or reaches around ears/jawline (bob/regular cut); "
            "'medium hair' = reaches neck or shoulders; "
            "'long hair' = extends past shoulders. "
            "If face_detected is false, default to 'short hair'."
        ),
    )
    hair_style_details: str = Field(
        ...,
        description=(
            "Comma-separated Danbooru-style English tags for hair color, texture, cut, parting, or hairline "
            "(e.g., 'dark hair, straight hair, receding hairline'). "
            "STRICTLY FORBIDDEN: Any facial expression words (e.g., smile, laughing, angry, open mouth). "
            "If face_detected is false, default to ''."
        ),
    )
    has_bangs: bool = Field(
        ...,
        description="True if bangs/fringe hang down over the forehead. False if forehead is exposed, swept back, or buzz cut. If face_detected is false, default to false.",
    )
    exposed_forehead: bool = Field(
        ...,
        description="True if forehead is clearly exposed/visible. False if covered by bangs. If face_detected is false, default to false.",
    )
    glasses: Literal["none", "glasses", "sunglasses"] = Field(
        ...,
        description="Eyewear type. Default to 'none' if none or if face_detected is false.",
    )
    facial_hair: Literal["none", "stubble", "beard", "mustache"] = Field(
        ...,
        description="Facial hair type. Default to 'none' if none or if face_detected is false.",
    )
```

---

### 2.2 `SYSTEM_PROMPT` の修正

`3. FOREHEAD & BANGS:` の下に、`4. HAIR LENGTH CRITERIA (CRITICAL FOR SHORT HAIR vs BUZZ CUT):` を追加する。前髪がある画像（`yae.jpg` 等）が誤ってベリーショートにならないよう、前髪との整合性ルールも明記する。

```python
SYSTEM_PROMPT = """You are an expert anime character designer and physical trait extractor for Animagine XL.
Analyze the user's portrait photograph and extract ONLY their static physical appearance.

CRITICAL INSTRUCTIONS:
1. FACE DETECTION & DEFAULTS:
   - If a clear human face is visible, set `face_detected` to true.
   - If NO face is present, or the face is covered by hands/objects or unidentifiable, set `face_detected` to false.
     When `face_detected` is false, populate all other fields with exact defaults:
     gender_tag="1boy", hair_length="short hair", hair_style_details="", has_bangs=false, exposed_forehead=false, glasses="none", facial_hair="none".

2. STRICTLY NO FACIAL EXPRESSIONS OR EMOTIONS:
   - Facial expressions will be injected separately based on voice emotion.
   - DO NOT EVER include expression tags in `hair_style_details` or any other field.
   - FORBIDDEN WORDS: 'smile', 'smiling', 'laughing', 'grin', 'angry', 'frown', 'open mouth', 'closed mouth', 'neutral', 'serious', 'happy', 'sad', 'teeth', 'looking at viewer'.
   - `hair_style_details` must ONLY describe hair color, cut, hairline, and hair texture.

3. FOREHEAD & BANGS:
   - If bangs cover the forehead, set `has_bangs` = true, `exposed_forehead` = false.
   - If forehead is exposed, receding, buzz cut, swept back, or bald, set `has_bangs` = false, `exposed_forehead` = true.

4. HAIR LENGTH CRITERIA (CRITICAL FOR SHORT HAIR vs BUZZ CUT):
   - `bald`: Completely hairless crown/scalp.
   - `buzz cut`: Hair is shaved/clipped very close to the head (under 1 cm). Round skull contour is clearly visible, no hair strands hang down, ears and forehead are 100% exposed.
   - `very short hair`: Cropped close (1 to 3 cm, crew cut / sporty cut). Sides are tight, ears are completely clear, no bangs.
   - `short hair`: Hair is 4 to 15 cm with distinct locks/strands, such as a bob cut or standard boy/girl short cut that has bangs or reaches the ears/napeline.
   - RULE: If a person has closely cropped/shaved hair with NO hanging locks and completely exposed ears/forehead, you MUST select `buzz cut` or `very short hair`. NEVER classify a buzz cut as `short hair`. Conversely, if the person has bangs covering the forehead, `hair_length` must be at least `short hair`.

Output MUST strictly conform to the provided JSON schema."""
```

---

### 2.3 `rule_based_transform` 関数の修正

VLM が `buzz cut` または `very short hair` を返した場合に、`README.md` の Gate 1-A 基準（`buzz cut, very short hair, exposed forehead`）を満たすようタグを展開し、さらに超短髪時のみアホ毛・耳かかり・ボブ化を抑止するネガティブタグ（`ahoge, spiky hair, hair over ears, (bob cut:1.2)`）を `negative_hair_bias` に追加する。

```python
def rule_based_transform(extracted: FaceVlmExtraction) -> tuple[str, str, list[str]]:
    """
    抽出された特徴から physical_traits と negative_hair_bias を生成する。
    戻り値: (physical_traits, negative_hair_bias, detected_expression_warnings)
    """
    if not extracted.face_detected:
        return "", "", []

    traits: list[str] = [extracted.gender_tag]

    # 髪の長さタグの展開（超短髪時は Animagine XL の長髪化バイアスを抑えるため重ね掛け）
    if extracted.hair_length == "buzz cut":
        traits.extend(["buzz cut", "very short hair"])
    elif extracted.hair_length == "very short hair":
        traits.extend(["very short hair", "buzz cut"])
    elif extracted.hair_length == "bald":
        traits.append("bald")
    elif extracted.hair_length:
        traits.append(extracted.hair_length)

    # hair_style_details のパース & 表情タグの検知・サニタイズ
    expression_warnings: list[str] = []
    if extracted.hair_style_details:
        raw_items = [t.strip() for t in extracted.hair_style_details.split(",") if t.strip()]
        sanitized_items = []
        for item in raw_items:
            lower = item.lower()
            found_expr = [kw for kw in FORBIDDEN_EXPRESSION_KEYWORDS if kw in lower]
            if found_expr:
                expression_warnings.append(f"Excluded expression token '{item}' ({', '.join(found_expr)})")
            else:
                sanitized_items.append(item)
        if sanitized_items:
            traits.extend(sanitized_items)

    # 眼鏡
    if extracted.glasses in ("glasses", "sunglasses"):
        traits.append(extracted.glasses)

    # 髭
    if extracted.facial_hair in ("stubble", "beard", "mustache"):
        traits.append(extracted.facial_hair)

    # 額露出・前髪判定および超短髪ネガティブ判定
    neg_tokens: list[str] = []
    if not extracted.has_bangs or extracted.exposed_forehead:
        if "exposed forehead" not in [t.lower() for t in traits]:
            traits.append("exposed forehead")
        neg_tokens.extend(["(bangs:1.3)", "(fringe:1.3)", "hair over forehead"])

    if extracted.hair_length in ("buzz cut", "very short hair", "bald"):
        neg_tokens.extend(["ahoge", "spiky hair", "hair over ears", "(bob cut:1.2)"])

    negative_hair_bias = ", ".join(neg_tokens)

    # 重複タグ排除（大文字小文字を無視しつつ順序を維持）
    seen = set()
    deduped: list[str] = []
    for t in traits:
        clean = t.strip()
        low = clean.lower()
        if low and low not in seen:
            seen.add(low)
            deduped.append(clean)

    physical_traits = ", ".join(deduped)
    return physical_traits, negative_hair_bias, expression_warnings
```

---

## 3. 修正後の確認・Phase 1 再評価ステップ

1. `verify_step1_vlm.py` の構文エラーや型定義の不整合がないことを確認する。
2. Phase 1-A の再評価コマンドを実行できる状態にする（または実行して結果を確認する）：
   ```bash
   python verify_step1_vlm.py --faces-dir test_assets/faces --model gemma4:e2b
   ```
3. **Phase 1-A 再評価での確認基準**:
   - `koji-bose.jpg`: `hair_length` が `buzz cut` または `very short hair` となり、`physical_traits` に `buzz cut, very short hair` と `exposed forehead` が含まれ、`negative_hair_bias` に `(bangs:1.3), (fringe:1.3), hair over forehead, ahoge, spiky hair, hair over ears, (bob cut:1.2)` が出力されること。
   - `koji-women-.jpg`: `1girl, long hair` かつ `exposed_forehead: true` が維持されること。
   - `yae.jpg`: `1girl, short hair` かつ `has_bangs: true`、`negative_hair_bias` が空文字であることが維持されること。
   - `test_noface.jpg`: `face_detected: false` が維持されること。
4. Phase 1-A の再評価結果に基づき、`README.md` の「Gate 1-A 実測エビデンス」および「2.1 Phase 2 検証プロンプト一覧（`koji-bose.jpg`）」を最新出力に合わせて更新できるよう準備する。