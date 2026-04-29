#!/usr/bin/env python3
"""note.com network capture harness.

Opens a browser, logs you in (manual or via stored creds), then mirrors every
HTTP request and response into JSONL files so you can grep them later. The
intended use:

  - Find new endpoints note's editor calls (after they ship a feature).
  - Verify which cookies are required for an endpoint.
  - Capture the exact request/response shape for a flow we want to replicate.

Run:
  python scripts/recon.py [--out /tmp/note-recon] [--minutes 10]

Then in the visible browser, do the action you want to instrument
(create a draft, set paid wall, attach magazine, etc.). When the timer expires
or you close the browser, the captures are written out.

Files produced:
  - <out>/requests.jsonl   one line per request
  - <out>/responses.jsonl  one line per response (with body excerpt)
  - <out>/cookies.json     final cookie state from the browser context
  - <out>/summary.txt      grouped endpoint summary (counts + first-seen order)

Article 1: this script reads only YOUR own session traffic on note.com.
That is consistent with note's terms (own account use). Don't use it to
scrape other people's content.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/note-recon", help="output directory")
    parser.add_argument("--minutes", type=int, default=10, help="capture window in minutes")
    parser.add_argument("--headless", action="store_true", help="run headless (default: visible)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    req_log = out / "requests.jsonl"
    res_log = out / "responses.jsonl"
    cookies_log = out / "cookies.json"
    summary_log = out / "summary.txt"

    req_log.write_text("")
    res_log.write_text("")

    from playwright.async_api import async_playwright

    endpoint_counter: Counter[str] = Counter()
    seen_order: list[str] = []
    seen_set: set[str] = set()

    def _log(path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context()
        page = await context.new_page()

        async def on_request(request: Any) -> None:
            url = request.url
            if "note.com" not in url:
                return
            try:
                post_data = request.post_data
            except Exception:
                post_data = None
            entry = {
                "ts": time.time(),
                "method": request.method,
                "url": url,
                "headers": dict(request.headers),
                "post_data": post_data,
            }
            _log(req_log, entry)
            # Track endpoint patterns
            path = url.split("?", 1)[0]
            endpoint_counter[f"{request.method} {path}"] += 1
            key = f"{request.method} {path}"
            if key not in seen_set:
                seen_set.add(key)
                seen_order.append(key)

        async def on_response(response: Any) -> None:
            url = response.url
            if "note.com" not in url:
                return
            try:
                body = await response.text()
            except Exception:
                body = ""
            entry = {
                "ts": time.time(),
                "status": response.status,
                "url": url,
                "headers": dict(response.headers),
                "body_excerpt": body[:4000],
            }
            _log(res_log, entry)

        page.on("request", lambda req: asyncio.create_task(on_request(req)))
        page.on("response", lambda res: asyncio.create_task(on_response(res)))

        print(f"[recon] Opening note.com — log in if needed. Capturing for {args.minutes} min.")
        print(f"[recon] Files: {out}/")
        await page.goto("https://note.com/login", wait_until="domcontentloaded")

        try:
            await asyncio.sleep(args.minutes * 60)
        except KeyboardInterrupt:
            print("[recon] interrupted, dumping…")

        cookies = await context.cookies()
        cookies_log.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))

        await browser.close()

    # Summary
    lines = ["# note.com endpoint usage", ""]
    lines.append("## First-seen order")
    for endpoint in seen_order:
        lines.append(f"  {endpoint}")
    lines.append("")
    lines.append("## Frequency")
    for endpoint, count in endpoint_counter.most_common():
        lines.append(f"  {count:4d}  {endpoint}")
    summary_log.write_text("\n".join(lines))
    print(f"[recon] done. Summary at {summary_log}")


if __name__ == "__main__":
    asyncio.run(main())
