# 小説共有サイト

`.txt`（各話）から、ブラウザで読める静的な小説サイトを生成します。
GitHub に push すると GitHub Actions が自動でビルドし、GitHub Pages で公開します。
**外部依存なし**（Python 標準ライブラリのみ）。

## 2つの使い方

1. **自分のサイトとして公開**（`episodes/` に原稿を置いて GitHub Pages で公開）
2. **誰でもブラウザだけでアップロード＆共有** … `upload.html`
   - 公開URL: **https://fu-3.github.io/NovelSharing/upload.html**
   - zip / txt をドラッグ＆ドロップ → その場でサイト化（**送信なし・完全にブラウザ内処理**）
   - 内容を圧縮して **URL に埋め込む**ので、生成されたリンクを送るだけで誰でも読めます
   - 長い作品は「**🔗 短いリンクを作成**」で **58文字程度の短縮URL**に（後述の Cloudflare Worker を使用）
   - またはオフライン向けに「**HTMLファイルで保存**」でファイルごと共有も可能

## 短縮リンク（Cloudflare Workers + KV）

長い作品でも `https://fu-3.github.io/NovelSharing/upload.html#s=XXXXXXXX` のような
**短いURL**で共有できます。仕組み:

- `upload.html` の「短いリンクを作成」を押すと、圧縮済みデータを Worker に保存し、短いキーを受け取る
- 共有相手が `#s=キー` を開くと Worker からデータを取得して表示
- 保存先は **あなたの Cloudflare アカウントの KV**（`worker/` がそのコード）

### Worker の再デプロイ

`worker/worker.js` を変更したときは:

```sh
cd worker
npx wrangler deploy
```

- 現在のエンドポイント: `https://novel-share.fu-3.workers.dev`
- URL を変えた場合は `build_site.py` の `SHORTENER_URL` を更新して push
- 無料枠の目安: KV 書き込み 1,000/日・読み取り 100,000/日・保存 1GB。データは 1 年で自動失効（`worker/worker.js` の `TTL_SECONDS`）
- 1 投稿の上限は 1.5MB（`MAX_BYTES`）

## 原稿の入れ方（2通り）

- `./episodes/` に `.txt` を直接置く
- `./incoming/` に **zip** を置く → ビルド時に中の `.txt` を自動で `episodes/` へ展開

文字コードは **UTF-8 / Shift-JIS が混在してOK**。
並び順はファイル名中の数字（「第12話」「012_」「12.」等）を数値として認識し、
数字が無ければ自然順（10話が2話より後）。

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
   Settings → Pages → Build and deployment → Source を **「GitHub Actions」** にする。

3. 完了。以後 `main` に push するたびに自動でビルド・公開されます。
   公開URL: `https://<ユーザー名>.github.io/<リポジトリ名>/`

## 原稿の追加・更新

`episodes/` に `.txt` を足すか、`incoming/` に zip を置いて push するだけ。

```sh
git add .
git commit -m "第N話を追加"
git push
```

zip を `incoming/` に入れて push した場合、Actions が自動で展開して `episodes/` に
コミットし直し（zip は削除）、そのまま公開します。

## 生成サイトの機能

- 🔗 **共有ボタン**（スマホは OS の共有シート、PC はリンクコピー / X / LINE）
- 🌙 **ダーク・ライト切替**（端末設定にも追従）
- 🔠 **文字サイズ調整** / ✍ **明朝・ゴシック切替** / 縦書き・横書き切替（設定は保存）
- 🔖 **しおり（続きから読む）** ・ ✓ **既読マーク** ・ 読書プログレスバー
- 🔍 目次の **検索フィルタ**、各話の **読了時間の目安**、**全話通し読み**ページ
- ⌨ キーボード操作（`←` 前の話 / `→` 次の話 / `t` 目次）、トップへ戻るボタン

## カスタマイズ

`build_site.py` 冒頭:
- `SITE_TITLE` … 目次の見出し
- `CHARS_PER_MIN` … 読了時間の計算（1分あたりの文字数）
