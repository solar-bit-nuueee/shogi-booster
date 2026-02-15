# shogi-booster

Flet + cshogi + やねうら王(USI) で「棋譜の解析 → 悪手抽出 → 復習(次の一手) → 優勢維持の対局練習」を行う、将棋上達支援アプリの試作です。

## セットアップ (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 起動

```powershell
flet run app.py
```

## 使い方(ざっくり)
- Engine path: 例 `C:/YO.exe` を入力して「エンジン接続」。
- 盤面はクリックで指し手入力(プロモーション選択あり)。
- 「解析(現在の手順)」で各手を固定時間で解析し、評価値差から悪手候補を抽出。
- 「復習」タブで次の一手問題として出題。
- 「優勢維持」タブで、指定局面からやねうら王相手に優位を維持/とがめる練習。

## 注意
- 本実装は最小構成のためUI/例外処理/棋譜ツリー表示は段階的に改善予定です。
