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

## ⚠️ 利用上の注意（やってはいけないこと）

このスキルは「自分の note アカウント」「自分の記事」を効率的に運用するためのものです。以下の用途には **絶対に使わないでください**。違法行為または重大な規約違反に該当する可能性があります。

### 🛑 絶対にやってはいけない（違法または重大な規約違反）

- **他人のアカウントを操作する**  
  → 不正アクセス禁止法違反（懲役3年以下または罰金100万円以下）。  
  本スキルは自分の認証 cookie でしか動かさないでください。
- **他人の有料記事を BOT で読破する / 取得する**  
  → 著作権侵害＋規約違反。読みたい記事は普通に購入してください。
- **他人のクリエイターのコンテンツを大量スクレイピングして再配布**  
  → 著作権侵害。
- **note.com のサーバに過剰負荷をかける**  
  → 偽計業務妨害罪の可能性（[岡崎市立中央図書館事件](https://ja.wikipedia.org/wiki/%E5%B2%A1%E5%B4%8E%E5%B8%82%E7%AB%8B%E4%B8%AD%E5%A4%AE%E5%9B%B3%E6%9B%B8%E9%A4%A8%E4%BA%8B%E4%BB%B6)を参照）。  
  note-mcp の rate limiter を外したり、並列リクエストで連打したりしないでください。

### ⚠️ 規約違反になり得るのでやらない

- **1日に何十〜何百記事も自動投稿してスパム化する**  
  → note 利用規約のスパム条項違反 → アカウント停止＆売上没収のリスク。  
  目安として **1日数本まで**、人間が手作業でやれる範囲に留める。
- **自動「スキ」/ 自動フォロー / 自動コメント**  
  → 明確に規約違反として扱われるケースが報告されています（例: [中野英仁氏の解説](https://note.com/hidehito_n/n/n896a4a8aec03)）。本スキルではそのような機能を提供していませんし、追加もしないでください。
- **「必ず儲かる」系・誇大広告の記事を有料販売**  
  → note 規約で明示禁止。記事の中身は健全に。
- **本スキルを「note 自動運用 SaaS」として有料販売**  
  → 本リポジトリのライセンス（[LICENSE](./LICENSE)）で禁止。

### 🟢 むしろ推奨される使い方

- 自分の記事の執筆フローを省力化する
- 自分のメンバーシップ向け記事の量産
- 自社プロダクトに組み込んでクリエイターの執筆体験を改善する
- 受託案件で記事を効率的に納品する
- OSS として改善し PR を送る

### 🛡 安全に使うための運用ルール

1. **常に自分のアカウントだけ**を操作する
2. **rate limit を外さない**（note-mcp の既定値で十分）
3. **半年に1回 [note 利用規約](https://note.com/terms) を読み直す**
4. **note からメール警告が来たら即手動運用に戻す**
5. **大規模商用利用を考えるなら note 運営に事前相談**（サポート経由でメール）

### ⚖️ 法的補足

- 自分のアカウントを自分の cookie で操作することは **不正アクセス禁止法違反にはならない**（[警察庁解説](https://www.npa.go.jp/bureau/cyber/pdf/1_kaisetsu.pdf)）
- 公開 JS の解析・API 構造の特定は **著作権法 30条の4** で合法（[改正著作権法解説](https://www.it-houmu.com/archives/1747)）
- 利用規約違反は **民事のみ・刑事罰なし**（[制裁の解説](https://houmu-pro.com/contract/233/)）

ただし「合法だから何をしてもいい」ではありません。**良識ある個人利用の範囲**で使ってください。

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
