# 成功成美診所 官方網頁

純靜態單頁網站（HTML／CSS／少量 JavaScript），不需要資料庫或 API 金鑰。

- `index.html`：頁面文字與連結
- `assets/site.css`、`assets/site.js`：樣式、手機選單與頁內連結
- `assets/images/line-qr.png`：成功店官方 LINE QR Code
- `assets/images/doctor-chen.webp`、`doctor-chang.webp`、`doctor-kao.webp`：醫師照片（陳炳諴、張峻愷、高傳紘）
- `scripts/validate_site.py`：檢查發布檔案白名單、必要連結、三位醫師卡片等；`--build <dir>` 輸出只含白名單檔案的資料夾
- `tests/`：`python3 -m unittest discover -s tests -v`

## 待補資料
- 陳炳諴醫師的學歷
- 內視鏡開辦後，更新「檢查與設備」
- 正式網址確定後，補上 canonical 與社群分享（og）設定

本站只放公開資訊（電話、地址、LINE ID、QR Code、地圖連結）。
