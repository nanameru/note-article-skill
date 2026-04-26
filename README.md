# note-article-skill

Claude Code / Cursor / その他 MCP 対応エージェントで使える **note.com 記事の企画〜執筆〜サムネ生成〜投稿** を一気通貫で行うスキルです。

ユーザーが「note 記事を書いて」と頼むと、ヒアリング → 構成案 → 本文執筆 → サムネ生成 → 下書き作成 → アイキャッチ設定、までを対話的に進めます。公開前には必ずユーザーの許可を取るガードレール付きです。

## 前提

- MCP クライアント（Claude Code など）がセットアップ済み
- [`note-mcp`](https://github.com/drillan/note-mcp) がインストール＆登録済み
- `codex` MCP が登録済み（サムネ生成に使用。Codex のサブスクリプション内で画像生成するため **OpenAI API キーは不要**）
- macOS の `sips` または ImageMagick（アイキャッチのアスペクト比調整に使用）

## インストール

### 方法1: Vercel Skills CLI（推奨）

```bash
npx skills add nanameru/note-article-skill
```

### 方法2: 手動

```bash
git clone https://github.com/nanameru/note-article-skill.git
cp -R note-article-skill/skills/note-article ~/.claude/skills/
```

プロジェクト単位で使いたい場合は `.claude/skills/` 以下に配置してください。

## 使い方

Claude Code で以下のように呼び出します：

```
/note-article
```

または自然言語で：

```
note 記事を書いて
```

対話的にヒアリング → 構成案 → 本文執筆と進み、合意を取りながら進行します。

## フロー

1. **ヒアリング**: テーマ、ターゲット、文字数、口調、サムネ有無などを確認
2. **構成案の合意**: H2/H3 レベルの目次を提示し、確認を取る
3. **本文執筆**: note 互換の Markdown で執筆
4. **サムネ生成**: Codex MCP に委譲（Codex のサブスク内で完結）
5. **下書き作成**: `note_create_draft` で下書き作成
6. **アイキャッチアップロード**: 1280:670 にクロップ後、アップロード
7. **本文画像の挿入**（任意）
8. **公開確認**: ユーザーの明示許可後のみ公開

## 重要な注意点

### アイキャッチは 1280:670 必須

note.com のアイキャッチは **アスペクト比 1280:670 が必須** です。推奨ではなく必須で、違う比率だと API がエラーを返します（`note-mcp` 経由だと `API response missing required field 'url'` という誤解を招くメッセージになります）。

スキル内では `sips` で自動的にクロップ + リサイズしてからアップロードします。

### 公開前の確認

このスキルは `note_publish_article` を**ユーザーの明示許可なしには絶対に呼びません**。下書き URL を提示し、プレビュー確認を促してから、ユーザーが「公開して」と返したときにのみ公開します。

## ファイル構成

```
skills/note-article/
├── SKILL.md                        # スキル本体（エージェント向け指示）
└── templates/
    ├── article.md                  # 記事テンプレート
    └── thumbnail_prompts.md        # サムネ生成プロンプト集

note-mcp-patches/                   # drillan/note-mcp への拡張パッチ
├── README.md                       # 適用方法
├── changes.patch                   # 当方が追加した差分のみ（git apply 用）
└── magazines.py                    # 新規（list_my_magazines, list_circle_plans）
```

`note-mcp-patches/` は、本スキルが利用する有料記事 / メンバーシップ / マガジン操作を有効にするためのパッチ群です。  
**drillan/note-mcp 本体は各自で clone してください**（このリポジトリには再配布していません）。詳細な手順は [note-mcp-patches/README.md](./note-mcp-patches/README.md) を参照してください。

## トラブルシュート

- **Google OAuth ログインが拒否される**: Playwright を Google が弾くため、メール + パスワード方式でログインしてください
- **`note_login` がタイムアウト**: デフォルト300秒では足りない場合 600秒に延長
- **アイキャッチ "API response missing required field 'url'"**: 真っ先にアスペクト比を疑う。1280:670 になっているか確認
- **Cookie 保存バグ**: `note-mcp` のバージョンによっては、ユーザー名自動取得失敗時に Cookie が保存されない既知バグあり。`note_set_username` で後から設定できます

## ライセンス

**note-article-skill License**（独自・ソース利用可能ライセンス／OSI 非承認）。詳細は [LICENSE](./LICENSE) を参照。

要点：

- ✅ **商用利用 OK**（自社プロダクト・受託案件・SaaS 等への組み込み可）
- ✅ **改変・派生物作成 OK**
- ✅ **再配布 OK**（ただし下記の条件を満たすこと）
- 🟦 **帰属表示が必須**：使用箇所のいずれか（README / About / LICENSE / NOTICE / 製品内ドキュメント）に以下を表示してください：
  > Built on [note-article-skill](https://github.com/nanameru/note-article-skill)
- 🛑 **再パッケージ販売の禁止**：本ソフトウェア（または実質的派生物）を、本リポジトリと競合する独立プロダクト／キット／有料マネージドサービスとして販売することはできません。  
  （より大きなアプリケーションの一部として組み込むのは可）
- 🛑 著作権・ライセンス表示の除去禁止

「自分の note 記事を書く / 案件で記事を量産する / 自社の AI 製品の一部に組み込む」のような **使い方は全部 OK** です。「これと同じ自動化キット」を再販売するのだけ NG です。

## 関連

- [drillan/note-mcp](https://github.com/drillan/note-mcp) — note.com MCP サーバー
- [Vercel Agent Skills](https://vercel.com/docs/agent-resources/skills)
- [skills.sh](https://skills.sh) — コミュニティスキルディレクトリ
