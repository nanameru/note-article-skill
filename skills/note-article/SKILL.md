---
name: note-article
description: note.com の記事を企画・執筆・サムネ生成・投稿まで一気通貫で行う。ユーザーが「note記事を書いて」「noteに投稿して」と頼んだときに使う。
---

# note-article — note.com 記事生成 & 投稿スキル

このスキルは `note-mcp`（drillan/note-mcp）と `codex` MCP を組み合わせて、note の記事をサムネ付きで生成・投稿するためのものです。画像生成は Codex のサブスクリプション内で完結するため、OpenAI API キーは不要です。

## 前提

以下がセットアップ済みであること。未セットアップなら README の手順へ案内する。

- `note-mcp` が MCP クライアントに登録されている（https://github.com/drillan/note-mcp）
- `note.com` に `note_login` 済み（Cookie が OS キーチェーンに保存済み）
- サムネ生成する場合: `codex` MCP が登録されている（Codex のサブスク内で画像生成できる）
- macOS: 画像リサイズに `sips`（macOS標準）または `ImageMagick` が利用できる

## MCP ツール一覧（note-mcp が提供）

| ツール | 用途 |
|---|---|
| `note_create_draft` | 下書き作成 |
| `note_update_article` | 記事の更新 |
| `note_publish_article` | 下書き→公開 |
| `note_upload_eyecatch` | アイキャッチ（サムネ）アップロード |
| `note_upload_body_image` | 本文埋め込み用画像アップロード |
| `note_insert_body_image` | 本文に画像挿入 |
| `note_login` | ブラウザログイン（初回のみ） |
| `note_check_auth` | 認証状態確認 |
| `note_set_username` | username を手動設定 |

## 実行フロー

ユーザーの要望を聞いて、以下のステップを順に実行する。途中でユーザーに確認する箇所は必ず止まること。

### Step 1: ヒアリング

次の情報を引き出す（明示されていなければ質問する）：

- **テーマ / ジャンル**（例: AI活用、副業、書評）
- **ターゲット読者**（例: AI初心者、エンジニア）
- **記事のゴール**（例: ノウハウ共有、集客、体験談）
- **文字数の目安**（例: 2000〜3000字）
- **口調**（例: ですます調 / だ・である調 / フランク）
- **公開形態**（下書き保存 / そのまま公開 / 有料）
- **サムネを生成するか**（Yes/No、Yesならテイスト指定）

### Step 2: 構成案を提示して合意を取る

見出し（H2, H3）レベルの構成案を Markdown で提示し、ユーザーに「この構成で書いていい？」と確認する。**ここで必ず止まる**。

### Step 3: 本文を執筆

合意した構成に従って Markdown で本文を書く。note互換の記法に注意：

- 数式は `$${...}$$`（KaTeX互換）
- 目次は `[TOC]`
- 外部URL埋め込みは URLを単独行に書くとリッチプレビューになる
- 本文画像を挟みたい箇所には `<!-- IMAGE: プロンプト -->` というプレースホルダーを残しておき、Step 7 で埋め込む

本文は `templates/article.md` を下敷きに使ってもよい。

### Step 4: サムネ生成（任意・Codex MCP 経由）

ユーザーがサムネ生成を希望した場合のみ。**Codex MCP のサブスク内で画像生成できるので、OpenAI API キーは不要**。独自の画像生成スクリプトは経由させない。

`mcp__codex__codex` を次のように呼ぶ：

```
prompt: |
  note 記事のアイキャッチ画像を1枚生成してください。あなた（Codex）の
  サブスク内で使える画像生成機能を直接使ってください。外部 API は呼びません。

  - アスペクト比: 16:9（後段で 1280:670 にクロップするため）
  - サイズ: 1536x1024 程度
  - 品質: 高品質
  - 出力先: thumbnails/thumb_note_<UNIX秒>.png （タイムスタンプ付きで上書きしない）

  プロンプト（英語）:
  "<画像の見た目を英語で具体的に>"

  最後に保存した絶対パスを1行で報告してください。

cwd: <ユーザーのプロジェクトルート>
sandbox: workspace-write
approval-policy: never
```

保存ファイル名は `thumbnails/thumb_note_<UNIX秒>.png` 形式で重複を避ける。返ってきた保存パスは Step 6 で使う。

### Step 5: note-mcp で下書き作成

`note_create_draft` を呼ぶ。引数はタイトル・本文（Markdown）・タグ。返り値として **記事ID** が返ってくるので必ず保持してユーザーにも明示する。

### Step 6: アイキャッチをアップロード（サムネ作った場合のみ）

**重要**: note.com のアイキャッチは **アスペクト比 1280:670 が必須**。違う比率だと API が `{"error":{"code":"invalid","message":"見出し画像は1280:670の縦横比の画像を設定してください"}}` を返し、note-mcp 側では `"API response missing required field 'url'"` という誤解を招くエラーに化けて見える。

アップロード前に **必ず 1280:670 にクロップ + リサイズ**する。macOS なら `sips` で完結：

```bash
SRC=thumbnails/thumb_note_<UNIX秒>.png
DST=thumbnails/thumb_note_<UNIX秒>_1280x670.png
cp "$SRC" "$DST"
# 元が 1672x941（16:9）の場合、1672x875 にクロップしてから 1280x670 にリサイズ
sips --cropToHeightWidth 875 1672 "$DST" >/dev/null
sips --resampleHeightWidth 670 1280 "$DST" >/dev/null
```

元のサイズが違う場合は `target_ratio = 1280/670 ≈ 1.91` に合わせてクロップ値を計算しなおす。

クロップ後の画像パスを `note_upload_eyecatch` に渡す。

### Step 7: 本文画像のアップロード & 挿入（必要な場合のみ）

本文に `<!-- IMAGE: ... -->` プレースホルダーがあれば：

1. **codex MCP** 経由で画像生成（Step 4 と同じ要領、用途に応じたサイズで）
2. `note_upload_body_image` でアップロード → 返ってくる Markdown 断片を取得
3. `note_update_article` でプレースホルダーを画像 Markdown に置換

### Step 8: ユーザーに確認して公開

下書き URL をユーザーに伝え、プレビュー確認を促す。ユーザーが「公開して」と言ったら `note_publish_article` を呼ぶ。**ユーザーの明示的な許可なく公開しない**。

公開時、ユーザーが希望すれば以下を一緒にセットする（`note_publish_article` の引数）：

- `magazine_keys`: マガジン追加（事前に `note_list_my_magazines` で一覧確認）
- `circle_plan_keys`: メンバーシップ限定にする（事前に `note_list_circle_plans` で一覧確認）
- `price`: 有料記事化（円）
- `separator_uuid`: 有料エリア開始位置（後述の自動選定を使う）
- `limited`: `True` で有料モード ON

### Step 8.5: 有料記事の自動セットアップ（ユーザーが「有料にして」と言った時）

ユーザーが価格設定を希望した場合、AI が「いい感じの位置」を自動で選ぶ。**ユーザーに位置を聞かない**（毎回聞かれるのが面倒なので任せる方針）。

**自動選定ルール**（このルールで AI が `separator_uuid` を決める）：

1. `note_get_separator_candidates` で本文の全ブロック UUID を取得（h2/h3/h4/p）
2. **h2 見出しだけを抽出**（粒度が荒いほうが自然な区切りになる）
3. 全 h2 の数が `n` 個のとき、**`floor(n * 0.4)` 番目の h2** を選ぶ（0-indexed）
   - 例: h2 が 6個なら `int(6 * 0.4) = 2` → 3番目の h2 がセパレータになる
   - 例: h2 が 4個なら `int(4 * 0.4) = 1` → 2番目の h2 がセパレータになる
4. ただし最初の h2 は必ず無料側に残す（読者を引き込むため）。1番目の h2 が選ばれそうになったら 2番目に繰り上げる
5. 最後の h2 もセパレータにしない（有料部分が空になるため）。最後が選ばれそうになったら手前に繰り下げる

**価格のデフォルト**:
- 「短めのノウハウ・体験談」: ¥300〜500
- 「具体的な手順を含む how-to」: ¥500〜1000
- 「長文の専門記事・複数のステップ」: ¥1000〜3000
- 迷ったら **¥500** を提案する

価格は **必ずユーザーに確認**してから設定する。位置は AI が自動選定して結果を伝えるだけで OK（不満があればその時に変更要求がくる）。

**選定結果は必ずユーザーに伝える**（例: 「『○○』の見出しから後ろを有料エリアにします」）。

## ガードレール

- **MUST**: Step 2（構成合意）と Step 8（公開許可）で必ず止まる
- **MUST**: 下書き作成後は記事 ID をユーザーに明示する
- **MUST**: サムネ生成は **codex MCP 経由**（`mcp__codex__codex`）。Claude から OpenAI API を直接叩かない
- **MUST**: アイキャッチは **1280:670 へクロップ + リサイズ** してからアップロード
- **NEVER**: note.com のログイン情報を扱おうとしない（Playwright がキーチェーンで管理）
- **NEVER**: 有料設定は明示指示がない限り付けない
- **NEVER**: ユーザーの明示許可なしに `note_publish_article` を呼ばない

## トラブルシュート

- **`note-mcp` のツールが見えない**: `.mcp.json` を確認 → Claude Code を再起動
- **ログインエラー / Google ログインが拒否される**: `accounts.google.com` が「このブラウザまたはアプリは安全でない可能性があります」と表示する場合、Playwright を Google が弾いている。**メールアドレス + パスワード方式でログイン**する
- **`note_login` がタイムアウト**: デフォルト300秒では足りないケースあり。600秒（10分）に延長して再実行
- **ログイン成功したが username が空**: 既知挙動（note-mcp のユーザー名自動取得が失敗するケースあり）。`note_set_username` で後から設定可
- **アイキャッチアップロードで "API response missing required field 'url'"**: 真っ先にアスペクト比を疑う。1280:670 になっているか確認
- **画像アップロード失敗**: ファイルサイズ（10MB以下）と形式（PNG/JPEG/GIF/WebP）を確認

## 参考

- drillan/note-mcp: https://github.com/drillan/note-mcp
- note アイキャッチ必須比率: **1280:670**（推奨ではなく必須）
