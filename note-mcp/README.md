# note-mcp-lite

note-article-skill のために書き起こした、**自己治癒型 MCP サーバ**。

## drillan/note-mcp との違い

| 項目 | drillan/note-mcp | note-mcp-lite |
|---|---|---|
| Cookie 保存先 | OS keyring | ファイル `~/.note-mcp-lite/session.json` (mode 0600) |
| Cookie 自動更新 | ❌（rotate を捕まえない） | ✅ **毎レスポンスで Set-Cookie を反映** |
| 401 時の挙動 | エラー → 手動ログイン必須 | ✅ **キーチェーンの認証情報で自動再ログイン** |
| 依存 | playwright + keyring + markdown-it + ... | playwright + keyring + markdown-it + httpx のみ |
| 行数 | 数千行 | 約 1000 行 |

「すぐ認証が切れて毎回ログインし直し」という課題を解決するのが主目的です。

## 仕組み（自己治癒の核）

note.com の `_note_session_v5` Cookie は **API リクエスト1回ごとに rotate** します。  
note-mcp-lite は `httpx` のレスポンスごとに `Set-Cookie` を捕まえてファイルに書き戻すので、**セッションが古くならない**。

それでも 401 が返ってきた場合は、OS キーチェーンに保存した email/password を使って **無人で Playwright を立ち上げ → 再ログイン → 同じリクエストをリトライ** します。

## インストール

```bash
cd /path/to/note-article-skill/note-mcp-lite
uv venv
uv pip install -e .
.venv/bin/playwright install chromium
```

または `pip install -e .` でも可（Python 3.11+）。

## MCP 登録

`~/.claude.json` の対象プロジェクトの `mcpServers` に追加：

```json
{
  "mcpServers": {
    "note-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/note-article-skill/note-mcp-lite",
        "python",
        "-m",
        "note_mcp_lite"
      ],
      "env": {}
    }
  }
}
```

サーバ名 `note-mcp` のままにしておくと、既存スキルの呼び出し（`mcp__note-mcp__note_login` 等）がそのまま動きます。

## 提供されるツール

| Tool | 説明 |
|---|---|
| `note_login` | Email + Password ログイン（自動 / 手動どちらも対応）。認証情報をキーチェーンに保存。 |
| `note_check_auth` | 現在の認証状態を返す |
| `note_logout` | セッション + 認証情報を削除 |
| `note_set_username` | username を手動セット（自動取得失敗時のフォールバック） |
| `note_list_articles` | 自分の記事一覧（draft / published フィルタ可） |
| `note_get_article` | 記事1件取得（HTML本文付き） |
| `note_create_draft` | Markdown から下書き作成 |
| `note_update_article` | 下書き本文更新 |
| `note_publish_article` | 公開（マガジン / メンバーシップ / 価格 / 有料ライン対応） |
| `note_get_separator_candidates` | 有料ライン候補のブロックUUID一覧 |
| `note_set_paid_settings` | 公開せずに価格 + 有料ライン位置を保存 |
| `note_delete_draft` | 下書き削除 |
| `note_upload_eyecatch` | アイキャッチ画像アップ（**1280:670 必須**） |
| `note_upload_body_image` | 本文用画像アップ（S3 経由） |
| `note_list_my_magazines` | 自分のマガジン一覧 |
| `note_list_circle_plans` | メンバーシッププラン一覧 |

## 既知の制限

- Markdown→HTML 変換は基本機能のみ（CommonMark + UUID付与）。drillan 版にあった **YouTube/Twitter 自動 embed** は未実装 — 必要なら埋め込み用 URL を直接 Markdown にペーストする運用で代用可。
- アイキャッチの **1280:670 強制** は MCP 内で行わない。アップロード前に skill 側（`sips` 等）でクロップしておく必要があります。
- セッションファイルが破損した場合は `~/.note-mcp-lite/session.json` を削除して `note_login` から再開。

## ライセンス

[note-article-skill License](../LICENSE)（ソース利用可・帰属表示必須・再パッケージ販売禁止）に従います。

## クレジット

API エンドポイントの構造（`/v1/text_notes/draft_save` の挙動など）は [drillan/note-mcp](https://github.com/drillan/note-mcp) を参考にリバースエンジニアリングを進めました。本実装はゼロから書き起こしたオリジナルですが、上流の知見に深く感謝します。
