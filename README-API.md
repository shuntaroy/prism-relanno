# HeaRT-API

可視化システム HeaRT で表示するための時系列データを返す API サーバです．

- Python 3.6-3.8 で動作確認しています．
- `requirements.txt` で指定された python ライブラリを仮想環境などにインストールしてください: `pip install -r requirements.txt`
- `uvicorn main:app` で起動できます (`main.py` が API の実態です)
- この API の他に，JaMIE が動作する API が必要です
  - POST で変数 text を受け付け，返戻 JSON が次の仕様を満たすこと
    - 成功時: `{"status": "Success", "text": "PRISMアノテーション仕様XML形式に準拠した解析結果"}`
    - 失敗時: `{"status": "Failure", "error": "エラーメッセージ"}`
  - `main.py` の global 変数 `JAMIE` に，その API の URL を指定してください

入力 POST

```
{
    "text": "時系列解析する医学テキスト"
    "dct": "文書作成日(DCT)を表す日付表現 YYYY-MM-DD (optional)"
}
```

出力 (JSON)

```
{
    "status": "Success",
    "response": HeaRT向けの時系列配列データ
}
```

なんらかのエラーがあるときは

```
{
    "status": "Failure",
    "message": "エラーメッセージ"
}
```

を返します．
