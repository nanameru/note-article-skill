"""FastMCP server for note-mcp.

Exposes the same tool names as drillan/note-mcp where possible (note_login,
note_check_auth, note_create_draft, etc.), so the existing note-article-skill
keeps working without changes.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from note_mcp import articles as articles_api
from note_mcp import auth as auth_module
from note_mcp import images as images_api
from note_mcp import magazines as magazines_api
from note_mcp import session as session_store
from note_mcp.client import AuthError, NoteAPIError

mcp: FastMCP = FastMCP("note-mcp")


def _format_error(exc: Exception) -> str:
    if isinstance(exc, AuthError):
        return f"AuthError: {exc}"
    if isinstance(exc, NoteAPIError):
        return f"APIError({exc.status}): {exc}"
    return f"{type(exc).__name__}: {exc}"


# ----- auth -----


@mcp.tool()
async def note_login(
    email: Annotated[str | None, "note.com のメールアドレス。省略すると手動ログイン待機"] = None,
    password: Annotated[str | None, "パスワード。省略すると手動ログイン待機"] = None,
    timeout: Annotated[int, "手動ログイン時のタイムアウト秒数。デフォルト600"] = 600,
    headless: Annotated[bool, "ヘッドレスで実行（手動ログイン時はFalse推奨）"] = False,
) -> str:
    """note.com にログインし、Cookie + 認証情報を保存します。

    email/password を指定すると自動ログイン → 認証情報をキーチェーンに保存。
    以降は API 401 が出ても自動的に再ログインで自己回復します。
    """
    try:
        result = await auth_module.login_with_browser(
            email=email,
            password=password,
            timeout=timeout,
            headless=headless,
        )
        username = result.get("username") or "(unknown)"
        return f"ログイン成功。username={username}, 保存されたcookie={result['cookies_saved']}"
    except Exception as exc:
        return _format_error(exc)


@mcp.tool()
async def note_check_auth() -> dict[str, Any]:
    """現在の認証状態を実 API で検証します（cookieが死んでいたらここで分かる）。"""
    saved = session_store.load_session() or {}
    cookies = saved.get("cookies") or {}
    if not cookies.get("_note_session_v5"):
        return {
            "authenticated": False,
            "reason": "no _note_session_v5 cookie",
            "hint": "note_login を実行してください。",
        }
    try:
        from note_mcp.whoami import verify_auth

        info = await verify_auth()
        # Persist the latest username so list_my_magazines etc. always have it
        saved["username"] = info.get("urlname", saved.get("username", ""))
        if info.get("user_id"):
            saved["user_id"] = info["user_id"]
        session_store.save_session(saved)
        return {
            "authenticated": True,
            "username": info.get("urlname", ""),
            "user_id": info.get("user_id", ""),
            "cookie_count": len(cookies),
        }
    except Exception as exc:
        return {
            "authenticated": False,
            "reason": _format_error(exc),
            "hint": "セッションが切れている可能性。note_login を実行してください。",
        }


@mcp.tool()
async def note_whoami() -> dict[str, Any]:
    """API経由で現在のユーザー情報を取得 + セッションに保存します。"""
    try:
        from note_mcp.whoami import refresh_username_in_session

        username = await refresh_username_in_session()
        saved = session_store.load_session() or {}
        return {
            "username": username,
            "user_id": saved.get("user_id", ""),
        }
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_logout() -> str:
    """セッション + 保存された認証情報を削除します。"""
    session_store.clear_session()
    session_store.clear_credentials()
    return "ログアウトしました（セッション・認証情報を削除）。"


@mcp.tool()
async def note_set_username(
    username: Annotated[str, "note のURL名（例: nanataitai）"],
) -> str:
    """ユーザー名を手動セット（自動取得失敗時のフォールバック）。"""
    saved = session_store.load_session() or {}
    saved["username"] = username
    session_store.save_session(saved)
    return f"username={username} を保存しました。"


# ----- articles -----


@mcp.tool()
async def note_list_articles(
    status: Annotated[str | None, '"draft" / "published" / 未指定で全件'] = None,
    page: Annotated[int, "ページ番号（1始まり）"] = 1,
    limit: Annotated[int, "1ページあたりの最大件数（max 10）"] = 10,
) -> dict[str, Any]:
    """自分の記事一覧を返します。"""
    try:
        return await articles_api.list_articles(status=status, page=page, limit=limit)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_get_article(
    article_id: Annotated[str, "記事key（n…形式）"],
) -> dict[str, Any]:
    """記事を取得（HTML本文付き）。"""
    try:
        return await articles_api.get_article(article_id)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_create_draft(
    title: Annotated[str, "タイトル"],
    body_markdown: Annotated[str, "Markdown 本文"],
    tags: Annotated[list[str] | None, "タグ（# は不要）"] = None,
) -> dict[str, Any]:
    """下書きを新規作成します。"""
    try:
        return await articles_api.create_draft(
            title=title, body_markdown=body_markdown, tags=tags
        )
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_update_article(
    article_id: Annotated[str, "更新する記事のIDまたはkey"],
    title: Annotated[str, "タイトル"],
    body_markdown: Annotated[str, "Markdown 本文"],
    tags: Annotated[list[str] | None, "タグ"] = None,
) -> dict[str, Any]:
    """下書き本文を更新します（公開済み記事も draft_save で本文更新可、ただし反映には publish が必要）。"""
    try:
        return await articles_api.update_article(
            article_id, title=title, body_markdown=body_markdown, tags=tags
        )
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_publish_article(
    article_key: Annotated[str, "記事key（n…）"],
    tags: Annotated[list[str] | None, "公開時タグ"] = None,
    magazine_keys: Annotated[list[str] | None, "追加するマガジンkey"] = None,
    circle_plan_keys: Annotated[
        list[str] | None, "メンバーシップ限定にするplan key（複数可）"
    ] = None,
    price: Annotated[int | None, "有料記事の価格（円）"] = None,
    separator_uuid: Annotated[
        str | None, "有料ライン位置のブロックUUID。get_separator_candidates で取得"
    ] = None,
    limited: Annotated[bool | None, "True なら閲覧制限あり（メンバー限定など）"] = None,
    disable_comment: Annotated[bool | None, "コメントを無効化"] = None,
    title_override: Annotated[str | None, "タイトルを強制上書き"] = None,
) -> dict[str, Any]:
    """記事を公開します（既存下書き → 公開）。"""
    try:
        return await articles_api.publish_article(
            article_key,
            tags=tags,
            magazine_keys=magazine_keys,
            circle_plan_keys=circle_plan_keys,
            price=price,
            separator_uuid=separator_uuid,
            limited=limited,
            disable_comment=disable_comment,
            title_override=title_override,
        )
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_get_separator_candidates(
    article_key: Annotated[str, "記事key（n…）"],
) -> list[dict[str, str]]:
    """有料ライン候補（h2/h3/h4/p のブロックUUID + プレビュー）を返します。"""
    try:
        return await articles_api.get_separator_candidates(article_key)
    except Exception as exc:
        return [{"error": _format_error(exc)}]


@mcp.tool()
async def note_set_paid_settings(
    article_key: Annotated[str, "記事key（n…）"],
    price: Annotated[int | None, "価格（円）"] = None,
    separator_uuid: Annotated[str | None, "有料ライン位置のUUID"] = None,
) -> dict[str, Any]:
    """下書き状態のまま、価格と有料ラインを設定。"""
    try:
        return await articles_api.set_paid_settings(
            article_key, price=price, separator_uuid=separator_uuid
        )
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_delete_draft(
    article_key: Annotated[str, "記事key（n…）"],
) -> dict[str, Any]:
    """下書きを削除します（公開済みは削除不可）。"""
    try:
        return await articles_api.delete_draft(article_key)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_delete_all_drafts(
    confirm: Annotated[bool, "True で実削除。False ならプレビューのみ返す"] = False,
) -> dict[str, Any]:
    """下書きを一括削除します。デフォルトは preview モード。"""
    try:
        return await articles_api.delete_all_drafts(confirm=confirm)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_create_from_file(
    file_path: Annotated[str, "Markdownファイルの絶対パス（YAML frontmatter 対応）"],
    tags: Annotated[list[str] | None, "frontmatter のタグを上書き"] = None,
) -> dict[str, Any]:
    """Markdownファイルから下書きを作成します。"""
    try:
        return await articles_api.create_from_file(file_path, tags_override=tags)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_get_preview_url(
    article_key: Annotated[str, "記事key（n…）"],
) -> dict[str, Any]:
    """下書きのプレビューURLを発行します（ログイン不要で閲覧可能）。"""
    try:
        url = await articles_api.get_preview_url(article_key)
        return {"key": article_key, "preview_url": url}
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_get_preview_html(
    article_key: Annotated[str, "記事key（n…）"],
) -> dict[str, Any]:
    """下書きの実プレビューHTMLを取得します（レイアウト崩れ確認用）。"""
    try:
        html = await articles_api.get_preview_html(article_key)
        return {"key": article_key, "html": html, "length": len(html)}
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_show_preview(
    article_key: Annotated[str, "記事key（n…）"],
) -> dict[str, Any]:
    """下書きのプレビューを既定ブラウザで開きます。"""
    import subprocess

    try:
        url = await articles_api.get_preview_url(article_key)
        subprocess.Popen(["open", url])
        return {"key": article_key, "preview_url": url, "opened": True}
    except Exception as exc:
        return {"error": _format_error(exc)}


# ----- images -----


@mcp.tool()
async def note_upload_eyecatch(
    file_path: Annotated[str, "アイキャッチ画像の絶対パス（**1280:670 必須**）"],
    article_id: Annotated[str, "対象記事のIDまたはkey"],
) -> dict[str, Any]:
    """アイキャッチ画像をアップロードします。アスペクト比 1280:670 必須。"""
    try:
        return await images_api.upload_eyecatch(file_path, article_id)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_upload_body_image(
    file_path: Annotated[str, "本文用画像の絶対パス"],
) -> dict[str, Any]:
    """本文中に貼る画像をアップロード（S3経由）。返却URLを Markdown ![](url) で本文に埋め込みます。"""
    try:
        return await images_api.upload_body_image(file_path)
    except Exception as exc:
        return {"error": _format_error(exc)}


@mcp.tool()
async def note_insert_body_image(
    article_id: Annotated[str, "対象記事のkey（n…）"],
    file_path: Annotated[str, "画像の絶対パス"],
    caption: Annotated[str, "キャプション（空文字可）"] = "",
    width: Annotated[int, "幅 px"] = 620,
    height: Annotated[int, "高さ px"] = 457,
) -> dict[str, Any]:
    """画像をアップロードしつつ、記事本文末尾に <figure> として挿入します（一発コマンド）。"""
    try:
        uploaded = await images_api.upload_body_image(file_path)
        result = await articles_api.insert_body_image(
            article_id,
            uploaded["url"],
            caption=caption,
            width=width,
            height=height,
        )
        return {**result, "uploaded": uploaded}
    except Exception as exc:
        return {"error": _format_error(exc)}


# ----- magazines / memberships -----


@mcp.tool()
async def note_list_my_magazines() -> list[dict[str, Any]]:
    """自分のマガジン一覧（m* プレフィックス含む）。"""
    try:
        return await magazines_api.list_my_magazines()
    except Exception as exc:
        return [{"error": _format_error(exc)}]


@mcp.tool()
async def note_list_circle_plans() -> list[dict[str, Any]]:
    """自分のメンバーシップ（旧サークル）プラン一覧。"""
    try:
        return await magazines_api.list_circle_plans()
    except Exception as exc:
        return [{"error": _format_error(exc)}]
