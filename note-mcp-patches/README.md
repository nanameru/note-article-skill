# note-mcp 拡張パッチ

このディレクトリは、本スキルが活用する [drillan/note-mcp](https://github.com/drillan/note-mcp) に **ローカルパッチを当てる**ためのファイル群です。

> **再配布ポリシー**: 本ディレクトリには drillan/note-mcp のソースコードそのものは含めていません。`changes.patch` は当方が追加した差分（`+` 行）と適用に必要な最小限のコンテキストのみ、`magazines.py` は当方が新規作成した完全オリジナルファイルです。drillan/note-mcp 本体は各自で clone してください。

## 追加・変更内容

| 機能 | 追加 MCP ツール | 補足 |
|---|---|---|
| **マガジン一覧取得** | `note_list_my_magazines` | `m*` プレフィックスのマガジンも返す（`/v1/my/magazines` だけでは取得できないものをカバー） |
| **メンバーシッププラン一覧** | `note_list_circle_plans` | サブスクリプションプラン（旧サークル）の一覧 |
| **有料ライン候補取得** | `note_get_separator_candidates` | 本文中のブロック UUID（h2/h3/h4/p）と短いプレビューを返す |
| **下書きの有料設定** | `note_set_paid_settings` | 公開せずに `price` と `separator` を設定 |
| **公開ツール拡張** | `note_publish_article` | `magazine_keys` / `circle_plan_keys` / `price` / `separator_uuid` / `limited` / `disable_comment` パラメータを追加 |
| **Cookie 保存バグ修正** | （`auth/browser.py` パッチ） | ログイン直後のユーザー名取得失敗で Cookie が捨てられる問題を修正 |

## 適用手順

### 1. drillan/note-mcp を clone（または既存 clone を使用）

```bash
git clone https://github.com/drillan/note-mcp.git
cd note-mcp
```

### 2. パッチを適用

```bash
git apply /path/to/note-article-skill/note-mcp-patches/changes.patch
```

### 3. 新規ファイル（マガジン関連）を追加

`changes.patch` には新規ファイルは含まれていません。以下を別途コピーしてください：

```bash
cp /path/to/note-article-skill/note-mcp-patches/magazines.py src/note_mcp/api/magazines.py
```

### 4. Claude Code を再起動

これで新ツールが MCP として認識されます。

## 動作確認

パッチ適用＆Claude Code 再起動後、以下が呼べることを確認：

```
> note_list_my_magazines()
> note_list_circle_plans()
> note_get_separator_candidates(article_id="n123abc...")
> note_set_paid_settings(article_id="...", price=500, separator_uuid="...")
> note_publish_article(article_id="...", circle_plan_keys=["..."], price=500, separator_uuid="...", limited=True)
```

## 既知の前提

- 上記パッチは drillan/note-mcp の `main` ブランチ（v0 系）を想定。  
  上流が大きく変わると `git apply` が失敗するので、その場合はパッチを参考に手動マージしてください。
- 上書き前に元ファイルをバックアップしておくことを推奨。

## 上流への取り込み（PR 化）について

このパッチを drillan/note-mcp に Pull Request として提案するのは歓迎です。  
出す前に補強しておきたい項目：

- [ ] テストコード（pytest フィクスチャ + recorded fixtures）
- [ ] フィールド名の API stability チェック（`circle_permissions` のような内部フィールドは将来変わる可能性あり）
- [ ] エラーハンドリングの厚み（HTTP 422 / 401 / 403 などの分岐）
- [ ] ドキュメント（README + docstring 拡充）

PR 化が成功すれば、本ディレクトリ自体を削除して上流に揃えるのが理想です。

## ライセンスについて

- `magazines.py` および `changes.patch` は **本リポジトリのライセンス**（[../LICENSE](../LICENSE) — note-article-skill License、ソース利用可能・帰属表示必須・再パッケージ販売禁止）に従います
- drillan/note-mcp 自体のライセンス条項は drillan さんのリポジトリを参照してください  
  （2026-04 時点で LICENSE ファイルが置かれていないため、利用前に確認することを推奨）
