"""楽天市場の価格を取得して data/ に記録する。標準ライブラリのみ。

環境変数:
  RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / RAKUTEN_AFFILIATE_ID  (GitHub Secrets)
  SITE_URL       楽天アプリに登録したURL (Refererとして送る)
  RAKUTEN_ENDPOINT  省略時は新しい版から順に試す。指定すればその1つだけを使う。
使い方:
  python scripts/fetch_prices.py          # 本番
  python scripts/fetch_prices.py --mock   # 通信せずテスト用データで動作確認
"""
import json, os, sys, time, random, zlib, datetime as dt
import urllib.parse, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))
BASE = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/"
# 旧版 20220601 は提供終了済み(400 "API Configuration not found")。新しい版から順に試す。
ENDPOINTS = ([os.environ["RAKUTEN_ENDPOINT"]] if os.environ.get("RAKUTEN_ENDPOINT")
             else [BASE + "20260701", BASE + "20260401"])
ERRORS = []  # 今回の実行で起きたエラー(キー等は含めない)
MOCK = "--mock" in sys.argv


def load(path, default):
    p = ROOT / path
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(path, obj):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def call_api(extra):
    """成功すれば商品リスト(0件なら[])、失敗すれば None を返す。"""
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
    query = "?" + urllib.parse.urlencode(params)
    headers = {"Referer": site, "Origin": site.rstrip("/")}

    for ep in list(ENDPOINTS):
        for attempt in range(4):
            time.sleep(1.2)  # 連続アクセスの制限対策(1秒に1回程度)
            try:
                with urllib.request.urlopen(urllib.request.Request(ep + query, headers=headers), timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))
                if ep != ENDPOINTS[0]:
                    ENDPOINTS.remove(ep); ENDPOINTS.insert(0, ep)  # 動いた版を優先
                items = data.get("Items") or data.get("items") or []
                return [i.get("Item", i) for i in items]  # formatVersion差を吸収
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "ignore")[:200]
                if e.code == 429:  # 回数制限: 待って再試行
                    time.sleep(3 * (attempt + 1)); continue
                if e.code == 400 and "API Configuration not found" in body:
                    print(f"  この版は使えません: {ep.rsplit('/', 1)[-1]}"); break  # 次の版へ
                # URLはキーを含むので出力しない
                ERRORS.append(f"HTTP {e.code}: {body}")
                print(f"  API error {e.code}: {body}")
                return None
            except Exception as e:  # 通信失敗など
                ERRORS.append(f"{type(e).__name__}")
                print(f"  通信エラー: {type(e).__name__}")
                return None
    ERRORS.append("利用できるAPIバージョンが見つかりません")
    return None


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
    if items is None:
        return None
    ok = [i for i in items
          if i.get("itemPrice", 0) >= w.get("min_price", 0)
          and i.get("reviewCount", 0) >= cfg["min_reviews"]
          and float(i.get("reviewAverage", 0)) >= cfg["min_review_average"]]
    # 安さではなく「定番」(レビュー件数が最多)を選ぶ。同数なら安い方。
    return max(ok, key=lambda i: (i.get("reviewCount", 0), -i["itemPrice"])) if ok else None


def main():
    cfg = load("config/items.json", {})
    tracked = load("data/tracked.json", {})
    history = load("data/history.json", {})
    latest = load("data/latest.json", {})
    day = os.environ.get("FORCE_DATE") or dt.datetime.now(JST).strftime("%Y-%m-%d")
    now = f"{day} " + dt.datetime.now(JST).strftime("%H:%M")

    missing = []
    for w in cfg["watch"]:
        wid = w["id"]
        rec = tracked.get(wid)
        if rec is None:
            changed = False
        elif "keyword" in rec:
            changed = rec["keyword"] != w["keyword"]
        else:  # 検索語が未記録の旧データ: 承認済みなら据え置き、未承認なら選び直す
            changed = not w.get("approved")
            if not changed:
                rec["keyword"] = w["keyword"]
        if rec is None or changed:  # 初回または検索語の変更時: 候補を1件選んで固定
            c = pick_candidate(w, cfg)
            if not c:
                print(f"{wid}: 取得失敗" if ERRORS else f"{wid}: 条件に合う商品なし"); continue
            tracked[wid] = {"itemCode": c["itemCode"], "itemName": c["itemName"],
                            "keyword": w["keyword"], "approved": False}
            if changed:
                history[wid] = []  # 別商品になるので履歴は引き継がない
            print(f"{wid}: 候補を選定 -> {c['itemName'][:40]}")
            items = [c]
        else:
            items = call_api({"itemCode": tracked[wid]["itemCode"], "hits": 1})
        if not items:
            print(f"{wid}: 取得できず(在庫なし/終了の可能性)")
            if items is not None:
                missing.append(wid)
            continue
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
    # 取得エラーはレポートで警告するため記録する
    save("data/status.json", {"date": day, "errors": sorted(set(ERRORS)), "unavailable": missing})
    print(f"取得エラー: {len(ERRORS)}件")


if __name__ == "__main__":
    main()
