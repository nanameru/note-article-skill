# サムネ生成プロンプト集

note のアイキャッチ生成用のテンプレート。Codex MCP に渡す用。

## ベース

- アスペクト比: 16:9 相当で生成し、後段で **1280:670** にクロップ + リサイズ
- **文字は入れる**（タイトルの短縮版 or キーワード）。CTR が上がる
- **基本は英語表記**（画像生成モデルは日本語フォントが苦手）。短い固有名詞ならカタカナ可
- 視認性重視: 大胆なコントラスト、1つの主役

## テキスト指示の書き方

英語プロンプト内に **`Bold large text '{{文字列}}' in clean sans-serif font, centered, high contrast`** を含める。

文字列の決め方：

- 記事タイトルから核を抜き出す（例: 「2026年Q1〜Q2のClaude Code、ここまで進化していた話」→ `Claude Code 2026 Updates`）
- 4ワード以内、ぱっと読める長さ
- 日本語にする場合は4文字以内（例: `note × AI`）

## テイスト別プロンプト例

### ミニマル / Tech系

```
Minimalist flat illustration for a tech blog thumbnail. Subject: {{主役}}.
Background: soft gradient, off-white to pale blue. Clean geometric shapes,
generous negative space. Bold large text '{{タイトル英訳3〜4語}}' in clean
sans-serif font, top-left or centered, high contrast. 16:9 composition.
```

### ポップ / エンタメ系

```
Vivid pop-art thumbnail. Subject: {{主役}}. Saturated colors (magenta, yellow,
cyan), halftone texture, bold outlines. Bold large text '{{タイトル英訳3〜4語}}'
in chunky condensed sans-serif font, with thick black outline for legibility.
16:9 composition, centered subject.
```

### シック / ビジネス系

```
Sophisticated editorial thumbnail. Subject: {{主役}}. Muted palette
(navy, ivory, warm gray), soft shadows, minimal props. Magazine cover feel.
Bold large text '{{タイトル英訳3〜4語}}' in serif or modern grotesque font,
positioned bottom-left, neutral tone. 16:9 composition.
```

### 写真風

```
Photorealistic thumbnail, shallow depth of field. Subject: {{主役}}.
Natural lighting, warm tones, shot on 35mm. Bold large text '{{タイトル英訳3〜4語}}'
in clean sans-serif font, with subtle drop shadow for legibility against the
photographic background. 16:9 composition.
```

## 使い方

Claude からは **codex MCP（`mcp__codex__codex`）経由**で呼び出す。Codex は自身のサブスクリプション内で画像生成できるため、OpenAI API キーは不要。

codex に渡すプロンプト例：

```
note 記事のアイキャッチ画像を1枚生成してください。あなた（Codex）の
サブスク内で使える画像生成機能を直接使ってください。外部 API は呼びません。

- アスペクト比: 16:9 相当（後段で 1280:670 にクロップ）
- サイズ: 1536x1024 程度
- 品質: 高品質
- 出力: thumbnails/thumb_note_<UNIX秒>.png
- プロンプト: <上のテンプレートの{{}}を埋めたもの。テキストの内容と配置も
  英語プロンプト内で具体的に指示する>

保存した絶対パスを1行で報告してください。
```

## アップロード前のクロップ（必須）

note のアイキャッチは **1280:670** が必須。macOS なら `sips` で完結：

```bash
SRC=thumbnails/thumb_note_<UNIX秒>.png
DST=thumbnails/thumb_note_<UNIX秒>_1280x670.png
cp "$SRC" "$DST"
# 16:9 → 1.91:1 にクロップ（1672x941 の場合）
sips --cropToHeightWidth 875 1672 "$DST" >/dev/null
sips --resampleHeightWidth 670 1280 "$DST" >/dev/null
```

## テキストが文字化けした場合の対処

画像生成モデルは時々スペルミスや文字化けを起こします。対処手順：

1. 生成された画像を Read で確認（マルチモーダルで読める）
2. 文字が読めない場合は、Codex に `regenerate with the text rendered correctly: '{{文字列}}'` と再依頼
3. それでもダメなら短い英単語に切り替える（例: 「副業ノウハウ」→「Side Hustle」）
