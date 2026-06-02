#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テキストファイル（各話 .txt）から、ブラウザで読める小説サイトを静的生成するスクリプト。

入力 : ./episodes/*.txt （文字コードは UTF-8 / Shift-JIS が混在しうる）
出力 : ./public/index.html と各話の HTML

外部依存なし（Python 標準ライブラリのみ）。再実行で ./public/ を作り直す。
"""

import html
import re
import shutil
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────
# 設定
# ──────────────────────────────────────────────────────────────────────────
EPISODES_DIR = Path("episodes")
PUBLIC_DIR = Path("public")
SITE_TITLE = "小説"  # index の見出し。必要なら書き換えてください。

# 読み込みを試す文字コードの順番（要件どおり utf-8 → cp932）。
ENCODINGS = ("utf-8", "cp932")


# ──────────────────────────────────────────────────────────────────────────
# CSS（横書き・読みやすい行間/最大幅・日本語フォント・スマホ対応）
# ──────────────────────────────────────────────────────────────────────────
CSS = """\
:root {
  --max-width: 42rem;
  --bg: #fbfbf9;
  --fg: #1a1a1a;
  --muted: #6b6b6b;
  --link: #2b6cb0;
  --border: #e2e2dd;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: "Hiragino Kaku Gothic ProN", "Hiragino Sans",
               "Yu Gothic", "Yu Gothic UI", "Meiryo",
               "Noto Sans JP", system-ui, sans-serif;
  font-size: 1.0625rem;
  line-height: 1.9;
  letter-spacing: 0.02em;
}
.wrap {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 1.5rem 1.25rem 4rem;
}
h1 {
  font-size: 1.5rem;
  line-height: 1.5;
  margin: 1rem 0 2rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid var(--border);
}
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }

/* 目次 */
ul.toc { list-style: none; margin: 0; padding: 0; }
ul.toc li { border-bottom: 1px solid var(--border); }
ul.toc li a {
  display: block;
  padding: 0.85rem 0.25rem;
  color: var(--fg);
}
ul.toc li a:hover { color: var(--link); text-decoration: none; }
.count { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }

/* 本文 */
article p {
  margin: 0 0 1.25rem;
  text-indent: 1em;
}
article p.blank { height: 0.6rem; margin: 0; }

/* ナビ */
nav.episode-nav {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  margin: 2.5rem 0 0;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
  font-size: 0.95rem;
}
nav.episode-nav a,
nav.episode-nav span {
  flex: 1;
  text-align: center;
  padding: 0.6rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
}
nav.episode-nav span.disabled {
  color: #bbb;
  background: #f3f3f0;
}
nav.episode-nav a:hover { text-decoration: none; border-color: var(--link); }

.home-link { display: inline-block; margin-bottom: 1.5rem; font-size: 0.95rem; }

@media (max-width: 480px) {
  body { font-size: 1rem; line-height: 1.85; }
  .wrap { padding: 1rem 1rem 3rem; }
  nav.episode-nav { font-size: 0.85rem; }
}
"""


# ──────────────────────────────────────────────────────────────────────────
# ファイル読み込み
# ──────────────────────────────────────────────────────────────────────────
def read_text(path: Path) -> str:
    """utf-8 → cp932 の順で試して読む。どちらも失敗したら置換ありで読む。"""
    data = path.read_bytes()
    for enc in ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    # 最終手段：壊れた文字は置換して読み込む
    return data.decode("utf-8", errors="replace")


# ──────────────────────────────────────────────────────────────────────────
# ソートキー
# ──────────────────────────────────────────────────────────────────────────
def first_number(name: str):
    """
    ファイル名から「最初に現れる数字（全角含む）」を整数で返す。
    「第12話」「012_」「12.」等に対応。無ければ None。
    """
    # 全角数字を半角へ
    trans = str.maketrans("０１２３４５６７８９", "0123456789")
    name = name.translate(trans)
    m = re.search(r"\d+", name)
    return int(m.group()) if m else None


def natural_key(name: str):
    """数字部分を数値として扱う自然順ソートキー（10話が2話より後に来る）。"""
    trans = str.maketrans("０１２３４５６７８９", "0123456789")
    name = name.translate(trans)
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def sort_key(path: Path):
    """
    ファイル名中の数字を優先。数字があるものを先に、その値順。
    数字が無いものは自然順ソートで後ろにまとめる。
    """
    stem = path.stem
    num = first_number(stem)
    if num is not None:
        # (0, 数値, 自然順) … 数字ありを優先し、同値はファイル名で安定化
        return (0, num, natural_key(stem))
    return (1, 0, natural_key(stem))


# ──────────────────────────────────────────────────────────────────────────
# 本文 → 段落 HTML
# ──────────────────────────────────────────────────────────────────────────
def body_to_html(text: str) -> str:
    """
    改行・空行を段落として保持しつつ HTML エスケープ。
    連続する空行は段落区切り。各行は <p> として出力する。
    """
    # 改行コードを正規化
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    parts = []
    for line in lines:
        stripped = line.strip()
        if stripped == "":
            # 空行は余白用の段落
            parts.append('<p class="blank"></p>')
        else:
            parts.append("<p>{}</p>".format(html.escape(stripped)))
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────
# HTML テンプレート
# ──────────────────────────────────────────────────────────────────────────
def page_html(title: str, body: str, css_href: str) -> str:
    return """\
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css}">
</head>
<body>
<div class="wrap">
{body}
</div>
</body>
</html>
""".format(title=html.escape(title), css=css_href, body=body)


def build_index(episodes) -> str:
    items = []
    for ep in episodes:
        items.append(
            '  <li><a href="{href}">{title}</a></li>'.format(
                href=html.escape(ep["filename"]),
                title=html.escape(ep["title"]),
            )
        )
    body = (
        "<h1>{site}</h1>\n".format(site=html.escape(SITE_TITLE))
        + '<p class="count">全 {n} 話</p>\n'.format(n=len(episodes))
        + '<ul class="toc">\n'
        + "\n".join(items)
        + "\n</ul>"
    )
    return page_html(SITE_TITLE, body, "style.css")


def build_episode(ep, prev_ep, next_ep) -> str:
    # ナビ（先頭・末尾は無効化）
    if prev_ep:
        prev_html = '<a href="{href}">← 前の話</a>'.format(
            href=html.escape(prev_ep["filename"]))
    else:
        prev_html = '<span class="disabled">← 前の話</span>'

    if next_ep:
        next_html = '<a href="{href}">次の話 →</a>'.format(
            href=html.escape(next_ep["filename"]))
    else:
        next_html = '<span class="disabled">次の話 →</span>'

    nav = (
        '<nav class="episode-nav">\n'
        "  {prev}\n"
        '  <a href="index.html">目次</a>\n'
        "  {next}\n"
        "</nav>"
    ).format(prev=prev_html, next=next_html)

    body = (
        '<a class="home-link" href="index.html">← 目次へ戻る</a>\n'
        + "<h1>{title}</h1>\n".format(title=html.escape(ep["title"]))
        + "<article>\n{content}\n</article>\n".format(content=ep["body_html"])
        + nav
    )
    return page_html(ep["title"], body, "style.css")


# ──────────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────────
def slugify(stem: str, index: int) -> str:
    """安全なファイル名を生成。日本語はそのまま使えるが、記号は除去。"""
    name = re.sub(r'[\\/:*?"<>|#%&{}\s]+', "_", stem).strip("_")
    if not name:
        name = "episode_{:03d}".format(index)
    return name + ".html"


def main():
    if not EPISODES_DIR.is_dir():
        print("エラー: {} が見つかりません。".format(EPISODES_DIR), file=sys.stderr)
        sys.exit(1)

    txt_files = sorted(EPISODES_DIR.glob("*.txt"), key=sort_key)
    if not txt_files:
        print("エラー: {} に .txt がありません。".format(EPISODES_DIR), file=sys.stderr)
        sys.exit(1)

    # public/ を作り直す
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True)

    # CSS を書き出し
    (PUBLIC_DIR / "style.css").write_text(CSS, encoding="utf-8")

    # 各話データを構築
    episodes = []
    used_names = set()
    for i, path in enumerate(txt_files):
        title = path.stem  # .txt を除いたファイル名
        out_name = slugify(title, i)
        # 重複回避
        base, ext = out_name[:-5], ".html"
        n = 1
        while out_name in used_names:
            out_name = "{}_{}{}".format(base, n, ext)
            n += 1
        used_names.add(out_name)

        text = read_text(path)
        episodes.append({
            "title": title,
            "filename": out_name,
            "body_html": body_to_html(text),
        })

    # index.html
    (PUBLIC_DIR / "index.html").write_text(
        build_index(episodes), encoding="utf-8")

    # 各話ページ
    for i, ep in enumerate(episodes):
        prev_ep = episodes[i - 1] if i > 0 else None
        next_ep = episodes[i + 1] if i < len(episodes) - 1 else None
        (PUBLIC_DIR / ep["filename"]).write_text(
            build_episode(ep, prev_ep, next_ep), encoding="utf-8")

    print("完了: {} 話を生成しました → {}/".format(len(episodes), PUBLIC_DIR))
    for i, ep in enumerate(episodes, 1):
        print("  {:>3}. {}  ({})".format(i, ep["title"], ep["filename"]))


if __name__ == "__main__":
    main()
