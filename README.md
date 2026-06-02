# 小説共有サイト

`./episodes/` に置いた `.txt`（各話）から、ブラウザで読める静的サイトを生成します。
GitHub に push すると GitHub Actions が自動でビルドし、GitHub Pages で公開します。

## ローカルで確認

```sh
python build_site.py
cd public
python -m http.server 8000
# ブラウザで http://localhost:8000/
```

## GitHub で公開する（初回セットアップ）

1. **リポジトリを作成して push**

   ```sh
   git init
   git add .
   git commit -m "小説共有サイト"
   git branch -M main
   git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
   git push -u origin main
   ```

2. **GitHub Pages を有効化**

   リポジトリの **Settings → Pages** を開き、
   **Build and deployment → Source** を **「GitHub Actions」** に設定する。

3. これで完了。以後 `main` に push するたびに自動でビルド・公開されます。
   公開URLは `https://<ユーザー名>.github.io/<リポジトリ名>/` です。
   （Actions タブの「Build & Deploy to GitHub Pages」からも進捗・URLを確認できます）

## 原稿の追加・更新

`./episodes/` に `.txt` を追加・編集して push するだけ。

```sh
git add episodes
git commit -m "第N話を追加"
git push
```

- 文字コードは UTF-8 / Shift-JIS が混在してOK
- 並び順はファイル名中の数字（「第12話」「012_」「12.」等）を数値として認識
- `build_site.py` 冒頭の `SITE_TITLE` で目次の見出しを変更できます
