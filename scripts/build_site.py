"""data/ から公開ページ(index.html)・日次レポート・投稿下書きを作る。
approved が true の商品だけを公開・投稿対象にする(承認制)。"""
import json, html, os, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))


def load(p, d):
    f = ROOT / p
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else d


def yen(n):
    return f"{int(n):,}円"


def sparkline(prices, w=140, h=36):
    if len(prices) < 2:
        return '<span class="na">記録中</span>'
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or 1
    pts = [(round(i * (w - 4) / (len(prices) - 1) + 2, 1),
            round(h - 4 - (p - lo) * (h - 8) / span, 1)) for i, p in enumerate(prices)]
    path = " ".join(f"{x},{y}" for x, y in pts)
    x, y = pts[-1]
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="価格推移"><polyline points="{path}" fill="none" '
            f'stroke="currentColor" stroke-width="1.6"/><circle cx="{x}" cy="{y}" r="3" fill="currentColor"/></svg>')


def analyze(wid, hist, drop_pct):
    prices = [e["p"] for e in hist]
    now = prices[-1]
    prev = prices[-2] if len(prices) > 1 else None
    tags = []
    if len(prices) >= 7 and now <= min(prices):
        tags.append("記録中の最安値")
    if prev and now <= prev * (1 - drop_pct / 100):
        tags.append(f"前回比 {round((prev - now) * 100 / prev)}%下落")
    return now, prev, prices, tags


def main():
    cfg = load("config/items.json", {})
    tracked, hist, latest = load("data/tracked.json", {}), load("data/history.json", {}), load("data/latest.json", {})
    drop = cfg.get("drop_alert_percent", 5)
    now_s = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    names = {w["id"]: w["name"] for w in cfg["watch"]}

    rows, events, pending = [], [], []
    for wid, t in tracked.items():
        if wid not in latest:
            continue
        if not t.get("approved"):
            pending.append((wid, t["itemName"], latest[wid]["price"]))
            continue
        now, prev, prices, tags = analyze(wid, hist[wid], drop)
        L = latest[wid]
        rows.append((wid, names.get(wid, wid), L, now, prev, prices, tags))
        if tags:
            events.append((wid, names.get(wid, wid), L, now, prev, tags))

    # ---- 公開ページ ----
    items_html = ""
    for wid, name, L, now, prev, prices, tags in rows:
        badge = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in tags)
        items_html += f"""
<li>
  <div class="main">
    <h2>{html.escape(name)}</h2>
    <p class="sub">{html.escape(L['shop'])} ・ ポイント{L['pointRate']}倍 ・ レビュー {L['reviewAverage']}（{L['reviewCount']}件）</p>
    {badge}
  </div>
  <div class="trend">{sparkline(prices)}<span class="range">{yen(min(prices))} 〜 {yen(max(prices))}</span></div>
  <div class="buy"><b>{yen(now)}</b>
    <a href="{html.escape(L['url'])}" rel="sponsored nofollow noopener" target="_blank">楽天市場で見る</a></div>
</li>"""
    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>消耗品の最安値ウォッチ</title>
<meta name="description" content="日用品・消耗品の楽天市場での価格を毎日記録し、値下がりを知らせます。">
<style>
:root{{--bg:#f2f5f3;--ink:#13201b;--mute:#5b6b64;--line:#d3ddd8;--acc:#0b6b5a;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1714;--ink:#e6efeb;--mute:#93a59d;--line:#25342e;--acc:#4cc2a8;--card:#15201c}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 "Hiragino Sans","Yu Gothic","Noto Sans JP",sans-serif}}
main{{max-width:760px;margin:0 auto;padding:32px 18px 64px}}
h1{{font-size:1.5rem;margin:0 0 4px}}
.lead{{color:var(--mute);margin:0 0 20px}}
.pr{{border:1px solid var(--line);background:var(--card);padding:8px 12px;font-size:.85rem;color:var(--mute);margin-bottom:24px}}
ul{{list-style:none;margin:0;padding:0}}
li{{display:grid;grid-template-columns:1fr auto auto;gap:16px;align-items:center;background:var(--card);border:1px solid var(--line);padding:16px;margin-bottom:10px}}
h2{{font-size:1rem;margin:0}}
.sub{{margin:2px 0 6px;color:var(--mute);font-size:.82rem}}
.tag{{display:inline-block;background:var(--acc);color:var(--bg);font-size:.75rem;padding:1px 8px;margin-right:6px}}
.trend{{color:var(--acc);text-align:right;font-size:.75rem}} .trend svg{{display:block;margin-left:auto}}
.range,.na{{color:var(--mute)}}
.buy{{text-align:right}} .buy b{{display:block;font-size:1.3rem}}
.buy a{{color:var(--acc);font-size:.9rem}}
footer{{margin-top:28px;color:var(--mute);font-size:.8rem}}
@media (max-width:600px){{li{{grid-template-columns:1fr auto}} .trend{{grid-column:1/-1;text-align:left}} .trend svg{{margin-left:0}}}}
</style></head><body><main>
<h1>消耗品の最安値ウォッチ</h1>
<p class="lead">ティッシュ、水、おむつなど毎月買うものの価格を、毎朝記録しています。</p>
<p class="pr">【PR】このページには楽天アフィリエイトのリンクが含まれます。</p>
<ul>{items_html or '<li><div class="main"><h2>準備中です</h2><p class="sub">最初の価格が記録され次第、ここに表示します。</p></div></li>'}</ul>
<footer>最終更新：{now_s}（日本時間）。表示価格は取得時点のものです。購入前に必ず楽天市場の商品ページで価格・在庫・送料をご確認ください。</footer>
</main></body></html>"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")

    # ---- 日次レポート(GitHub Issueとして届く) ----
    r = [f"## 日次レポート {now_s}", "",
         f"- 公開中の商品: {len(rows)}件 / 承認待ち: {len(pending)}件",
         f"- 値下がり・最安検知: {len(events)}件", ""]
    if events:
        r.append("### 検知した商品")
        r += [f"- {n}: {yen(now)}（{'、'.join(tags)}）" for _, n, _, now, _, tags in events]
        r.append("")
    if pending:
        r.append("### 承認待ちの候補（data/tracked.json で approved を true にすると公開されます）")
        r += [f"- {wid}: {n[:50]} / {yen(p)}" for wid, n, p in pending]
        r.append("")
    r += ["### 未対応", "- クリック数・確定報酬は未接続です（次のステップで追加）。"]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "latest.md").write_text("\n".join(r), encoding="utf-8")

    # ---- 投稿下書き(自動投稿はしない。確認して手動で投稿) ----
    if events:
        (ROOT / "drafts").mkdir(exist_ok=True)
        d = ["# 投稿下書き（確認・修正してから手動で投稿してください）", ""]
        for _, n, L, now, prev, tags in events:
            d += [f"## {n}", "",
                  f"【PR】{n}が{'、'.join(tags)}。",
                  f"現在 {yen(now)}（{L['shop']}）" + (f"／前回 {yen(prev)}" if prev else ""),
                  L["url"],
                  f"※{L['fetchedAt']}時点の価格です。", ""]
        (ROOT / "drafts" / f"{dt.datetime.now(JST):%Y-%m-%d}.md").write_text("\n".join(d), encoding="utf-8")
    print(f"site: {len(rows)}件公開 / 承認待ち{len(pending)}件 / 検知{len(events)}件")


if __name__ == "__main__":
    main()
