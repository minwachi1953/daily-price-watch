"""楽天市場の価格を取得して data/ に記録する。標準ライブラリのみ。

環境変数:
  RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / RAKUTEN_AFFILIATE_ID  (GitHub Secrets)
  SITE_URL       楽天アプリに登録したURL (Refererとして送る)
  RAKUTEN_ENDPOINT  省略時は下の既定値。20220601版は2027-01-18廃止予定。
                    20260401版へ移行するときはここだけ変える(仕様差は要確認)。
使い方:
  python scripts/fetch_prices.py          # 本番
  python scripts/fetch_prices.py --mock   # 通信せずテスト用データで動作確認
"""
import json, os, sys, time, random, zlib, datetime as dt
import urllib.parse, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))
ENDPOINT = os.environ.get(
    "RAKUTEN_ENDPOINT",
    "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601")
MOCK = "--mock" in sys.argv


def load(path, default):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def call_api(extra):
    if MOCK:
        return mock_items(extra)
    site = os.environ["SITE_URL"]
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "format": "json", "formatVersion": 2, "availability": 1,
    }
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        params["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    params.update(extra)
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Referer": site, "Origin": site.rstrip("/")})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # キー類がログに出ないよう、URLは出さない
        print(f"  API error {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        return []
    time.sleep(1.1)  # 連続アクセスの制限対策
    items = data.get("Items") or data.get("items") or []
    return [i.get("Item", i) for i in items]  # formatVersion差を吸収


def mock_items(extra):
    key = extra.get("itemCode") or extra.get("keyword", "x")
    seed = int(os.environ.get("MOCK_DAY", dt.date.today().toordinal()))
    rnd = random.Random(f"{key}{seed}")
    base = 1000 + (zlib.crc32(key.split(":")[-1].split("-")[0].encode()) % 3000) // 10 * 10
    return [{
        "itemName": f"[MOCK] {key} {n}", "itemCode": f"mock:{key.split(':')[-1].split('-')[0]}-{n}",
        "itemPrice": base + rnd.randint(-120, 120) + n * 40,
        "itemUrl": "https://example.com/", "affiliateUrl": "https://example.com/?aff=1",
        "shopName": "モックショップ", "pointRate": 1,
        "reviewAverage": 4.4, "reviewCount": 120, "availability": 1,
    } for n in range(5)]


def pick_candidate(w, cfg):
    items = call_api({"keyword": w["keyword"], "hits": 30, "sort": "standard"})
    ok = [i for i in items
          if i.get("itemPrice", 0) >= w.get("min_price", 0)
          and i.get("reviewCount", 0) >= cfg["min_reviews"]
          and float(i.get("reviewAverage", 0)) >= cfg["min_review_average"]]
    return min(ok, key=lambda i: i["itemPrice"]) if ok else None


def main():
    cfg = load("config/items.json", {})
    tracked = load("data/tracked.json", {})
    history = load("data/history.json", {})
    latest = load("data/latest.json", {})
    day = os.environ.get("FORCE_DATE") or dt.datetime.now(JST).strftime("%Y-%m-%d")
    now = f"{day} " + dt.datetime.now(JST).strftime("%H:%M")

    for w in cfg["watch"]:
        wid = w["id"]
        if wid not in tracked:  # 初回: 候補を1件選んで固定(未承認)
            c = pick_candidate(w, cfg)
            if not c:
                print(f"{wid}: 条件に合う商品なし"); continue
            tracked[wid] = {"itemCode": c["itemCode"], "itemName": c["itemName"], "approved": False}
            print(f"{wid}: 候補を選定 -> {c['itemName'][:40]}")
            items = [c]
        else:
            items = call_api({"itemCode": tracked[wid]["itemCode"], "hits": 1})
        if not items:
            print(f"{wid}: 取得できず(在庫なし/終了の可能性)"); continue
        i = items[0]
        latest[wid] = {
            "itemName": i["itemName"], "price": i["itemPrice"], "shop": i.get("shopName", ""),
            "url": i.get("affiliateUrl") or i["itemUrl"], "pointRate": i.get("pointRate", 1),
            "reviewAverage": i.get("reviewAverage"), "reviewCount": i.get("reviewCount"),
            "fetchedAt": now,
        }
        h = history.setdefault(wid, [])
        h[:] = [e for e in h if e["d"] != day] + [{"d": day, "p": i["itemPrice"]}]
        print(f"{wid}: {i['itemPrice']}円")

    save("data/tracked.json", tracked)
    save("data/history.json", history)
    save("data/latest.json", latest)


if __name__ == "__main__":
    main()
