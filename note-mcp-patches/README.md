# note-mcp 拡張パッチ

このディレクトリは、本スキルが活用する [drillan/note-mcp](https://github.com/drillan/note-mcp) に対するローカル拡張パッチです。

## 追加・変更内容

| 機能 | 追加 MCP ツール | 補足 |
|---|---|---|
| **マガジン一覧取得** | `note_list_my_magazines` | `m*` プレフィックスのマガジンも返す（`/v1/my/magazines` だけでは取得できないものをカバー） |
| **メンバーシッププラン一覧** | `note_list_circle_plans` | サブスクリプションプラン（旧サークル）の一覧 |
| **有料ライン候補取得** | `note_get_separator_candidates` | 本文中のブロック UUID（h2/h3/h4/p）と短いプレビューを返す |
| **下書きの有料設定** | `note_set_paid_settings` | 公開せずに `price` と `separator` を設定 |
| **公開ツール拡張** | `note_publish_article` | `magazine_keys` / `circle_plan_keys` / `price` / `separator_uuid` / `limited` / `disable_comment` パラメータを追加 |
| **Cookie 保存バグ修正** | （`auth/browser.py` パッチ） | ログイン直後のユーザー名取得失敗で Cookie が捨てられる問題を修正 |

## 適用方法

### 方法1: ファイルを丸ごと上書き（最速）

drillan/note-mcp の clone に対して、以下の4ファイルを上書きコピー：

```bash
cd /path/to/your/note-mcp/clone

cp /path/to/note-article-skill/note-mcp-patches/src/note_mcp/api/articles.py    src/note_mcp/api/articles.py
cp /path/to/note-article-skill/note-mcp-patches/src/note_mcp/api/magazines.py   src/note_mcp/api/magazines.py
cp /path/to/note-article-skill/note-mcp-patches/src/note_mcp/server.py          src/note_mcp/server.py
cp /path/to/note-article-skill/note-mcp-patches/src/note_mcp/auth/browser.py    src/note_mcp/auth/browser.py
```

そのあと Claude Code を再起動すると、新ツールが MCP として認識されます。

### 方法2: パッチファイル経由

```bash
cd /path/to/your/note-mcp/clone
git apply /path/to/note-article-skill/note-mcp-patches/changes.patch
```

ただし、上流の note-mcp に大きな変更が入ると `git apply` は失敗するので、その場合は方法1で上書きしてください。

## 既知の前提

- 上記パッチは drillan/note-mcp の `main` ブランチ（v0 系）に適用することを想定。  
  メジャーバージョン更新後は、再度パッチを当て直す必要があります。
- 上書き前に元ファイルをバックアップしておくことを推奨：
  ```bash
  cp src/note_mcp/api/articles.py src/note_mcp/api/articles.py.bak
  ```

## 動作確認

パッチ適用＆Claude Code 再起動後、以下が呼べることを確認：

```
> note_list_my_magazines()
> note_list_circle_plans()
> note_get_separator_candidates(article_id="n123abc...")
> note_set_paid_settings(article_id="...", price=500, separator_uuid="...")
> note_publish_article(article_id="...", circle_plan_keys=["..."], price=500, separator_uuid="...", limited=True)
```

## 上流への取り込み（PR 化）について

ここの拡張内容を drillan/note-mcp に Pull Request として提案するのは歓迎です。  
ただし以下の項目を補強してから出すのが現実的です：

- [ ] テストコード（pytest フィクスチャ + recorded fixtures）
- [ ] フィールド名の API stability チェック（`circle_permissions` のような内部フィールドは将来変わる可能性あり）
- [ ] エラーハンドリングの厚み（HTTP 422 / 401 / 403 などの分岐）
- [ ] ドキュメント（README + docstring 拡充）
- [ ] `INVESTIGATOR_MODE` を使った API 探索ノート
