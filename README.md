# daily-price-watch

消耗品の楽天価格を毎朝記録し、公開ページ(index.html)・日次レポート(Issue)・投稿下書き(drafts/)を作ります。

## セットアップ
1. このフォルダの中身をすべてリポジトリにアップロードする(.github フォルダも含める)
2. Settings → Secrets and variables → Actions に次の3つを登録する
   - `RAKUTEN_APP_ID` / `RAKUTEN_ACCESS_KEY` / `RAKUTEN_AFFILIATE_ID`
3. Actions タブ → daily → Run workflow で手動実行して動作確認

## 運用
- 初回実行後、`data/tracked.json` に候補が出ます。商品を確認し、問題なければ `"approved": true` に変更すると公開されます。
- 投稿は自動では行いません。`drafts/` の下書きを確認して手動で投稿してください(PR表記は入っています)。
- 楽天APIの旧版(20220601)は2027-01-18に廃止予定です。移行時は `RAKUTEN_ENDPOINT` を新版に変更し、動作確認してください。

## ローカルで試す(通信なし)
    python scripts/fetch_prices.py --mock && python scripts/build_site.py
