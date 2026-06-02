#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テキスト（各話 .txt / .zip）から、ブラウザで読める小説サイトを静的生成する。

入力:
  ./episodes/*.txt          各話のテキスト（UTF-8 / Shift-JIS 混在可）
  ./incoming/*.zip          zip を置くと中の .txt を episodes/ へ自動展開（任意）

出力:
  ./public/                 index.html / all.html / 各話HTML / style.css / app.js

特徴:
  外部依存なし（Python 標準ライブラリのみ）。再実行で public/ を作り直す。
  生成サイトの便利機能:
    - 共有ボタン（Web Share API / リンクコピー / X / LINE）
    - ダーク・ライト切替、文字サイズ調整、明朝/ゴシック切替、縦書き/横書き切替（設定は保存）
    - しおり（続きから読む）・既読マーク・読書プログレスバー
    - 目次の検索フィルタ、読了時間の目安、全話通し読みページ
    - キーボード操作（← 前 / → 次 / t 目次）、トップへ戻る
"""

import html
import re
import shutil
import sys
import zipfile
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────
# 設定
# ──────────────────────────────────────────────────────────────────────────
EPISODES_DIR = Path("episodes")
INCOMING_DIR = Path("incoming")
PUBLIC_DIR = Path("public")
SITE_TITLE = "小説"          # 目次の見出し。自由に変更可。
CHARS_PER_MIN = 500          # 読了時間の目安（日本語：1分あたりの文字数）
ENCODINGS = ("utf-8", "cp932")  # 読み込みを試す順（utf-8 → Shift-JIS）


# ──────────────────────────────────────────────────────────────────────────
# 文字コード対応の読み込み
# ──────────────────────────────────────────────────────────────────────────
def decode_bytes(data: bytes) -> str:
    for enc in ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_text(path: Path) -> str:
    return decode_bytes(path.read_bytes())


# ──────────────────────────────────────────────────────────────────────────
# zip の自動展開（incoming/*.zip → episodes/*.txt）
# ──────────────────────────────────────────────────────────────────────────
def _zip_name(info: zipfile.ZipInfo) -> str:
    """zip 内ファイル名を復号。Windows製 zip の Shift-JIS 名にも対応。"""
    name = info.filename
    if info.flag_bits & 0x800:        # UTF-8 フラグ
        return name
    try:
        return name.encode("cp437").decode("cp932")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def extract_zips() -> int:
    """incoming/ 内の zip から .txt を episodes/ へ展開。展開した数を返す。"""
    if not INCOMING_DIR.is_dir():
        return 0
    zips = sorted(INCOMING_DIR.glob("*.zip"))
    if not zips:
        return 0
    EPISODES_DIR.mkdir(exist_ok=True)
    total = 0
    for zpath in zips:
        n = 0
        try:
            with zipfile.ZipFile(zpath) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = _zip_name(info)
                    base = Path(name).name           # パス区切りを除去（traversal対策）
                    if not base.lower().endswith(".txt"):
                        continue
                    if base.startswith("._") or "__MACOSX" in name:
                        continue
                    (EPISODES_DIR / base).write_bytes(zf.read(info))
                    n += 1
            total += n
            print("展開: {} から {} 件".format(zpath.name, n))
        except zipfile.BadZipFile:
            print("警告: 壊れた zip をスキップ: {}".format(zpath), file=sys.stderr)
    return total


# ──────────────────────────────────────────────────────────────────────────
# ソート（ファイル名中の数字を数値として）
# ──────────────────────────────────────────────────────────────────────────
_Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def first_number(name: str):
    m = re.search(r"\d+", name.translate(_Z2H))
    return int(m.group()) if m else None


def natural_key(name: str):
    s = name.translate(_Z2H)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def sort_key(path: Path):
    stem = path.stem
    num = first_number(stem)
    if num is not None:
        return (0, num, natural_key(stem))
    return (1, 0, natural_key(stem))


# ──────────────────────────────────────────────────────────────────────────
# 本文 → 段落HTML（改行・空行を保持、HTMLエスケープ）
# ──────────────────────────────────────────────────────────────────────────
def body_to_html(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = []
    for line in text.split("\n"):
        s = line.strip()
        if s == "":
            parts.append('<p class="blank"></p>')
        else:
            parts.append("<p>{}</p>".format(html.escape(s)))
    return "\n".join(parts)


def count_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def reading_minutes(chars: int) -> int:
    return max(1, round(chars / CHARS_PER_MIN))


# ──────────────────────────────────────────────────────────────────────────
# 出力ファイル名
# ──────────────────────────────────────────────────────────────────────────
def slugify(stem: str, index: int) -> str:
    name = re.sub(r'[\\/:*?"<>|#%&{}\s]+', "_", stem).strip("_")
    if not name:
        name = "episode_{:03d}".format(index)
    return name


# ──────────────────────────────────────────────────────────────────────────
# 共通テンプレート
# ──────────────────────────────────────────────────────────────────────────
TOOLBAR_HTML = """\
<header class="toolbar">
  <a class="brand" href="index.html">\U0001F4DA 目次</a>
  <div class="tools">
    <button id="btn-theme" class="tbtn" type="button"></button>
    <button data-share class="tbtn" type="button" title="共有">\U0001F517 共有</button>
    <button id="btn-settings" class="tbtn" type="button" aria-label="設定" title="表示設定">⚙</button>
  </div>
  <div id="settings-panel" class="panel">
    <div class="row"><span>文字サイズ</span><span class="grp">
      <button id="btn-fontminus" class="sbtn" type="button">A−</button>
      <button id="btn-fontreset" class="sbtn" type="button">標準</button>
      <button id="btn-fontplus" class="sbtn" type="button">A＋</button></span></div>
    <div class="row"><span>書体</span><button id="btn-font" class="sbtn" type="button"></button></div>
    <div class="row"><span>組方向</span><button id="btn-mode" class="sbtn" type="button"></button></div>
    <div class="row"><span>この作品を共有</span><span class="grp">
      <a data-share-x class="sbtn" role="button">X</a>
      <a data-share-line class="sbtn" role="button">LINE</a>
      <button data-share class="sbtn" type="button">リンク</button></span></div>
  </div>
</header>"""

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="ja" data-page="%PAGE%">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>%TITLE%</title>
<link rel="stylesheet" href="style.css">
<script>
/* 描画前に保存済みの表示設定を適用（ちらつき防止） */
(function(){try{var d=document.documentElement,s=localStorage;
if(s.theme)d.dataset.theme=s.theme;
if(s.font)d.dataset.font=s.font;
if(s.mode)d.dataset.mode=s.mode;
if(s.fscale)d.style.setProperty('--user-scale',s.fscale);}catch(e){}})();
</script>
</head>
<body %BODYATTR%>
%TOOLBAR%
<div id="progress"><div id="progress-bar"></div></div>
<main class="wrap">
%BODY%
</main>
<button id="to-top" type="button" aria-label="先頭へ戻る" title="先頭へ">↑</button>
<script src="app.js" defer></script>
</body>
</html>
"""


def page_html(title: str, body_inner: str, page_type: str, body_attrs: str = "") -> str:
    out = PAGE_TEMPLATE
    out = out.replace("%PAGE%", page_type)
    out = out.replace("%BODYATTR%", body_attrs)
    out = out.replace("%TITLE%", html.escape(title))
    out = out.replace("%TOOLBAR%", TOOLBAR_HTML)
    out = out.replace("%BODY%", body_inner)
    return out


# ──────────────────────────────────────────────────────────────────────────
# 各ページ生成
# ──────────────────────────────────────────────────────────────────────────
def build_index(episodes, total_chars) -> str:
    rows = []
    for i, ep in enumerate(episodes, 1):
        rows.append(
            '<li data-id="{id}" data-title="{title}">'
            '<a href="{id}.html">'
            '<span class="num">{i}</span>'
            '<span class="ti">{title}</span>'
            '<span class="meta">{chars:,}字・約{mins}分</span>'
            "</a></li>".format(
                id=html.escape(ep["id"]),
                title=html.escape(ep["title"]),
                i=i,
                chars=ep["chars"],
                mins=ep["mins"],
            )
        )

    body = (
        "<h1>{site}</h1>\n".format(site=html.escape(SITE_TITLE))
        + '<div id="resume" class="resume" style="display:none">'
        '<span class="resume-text">続きから：<b class="t"></b> '
        '<span class="p"></span></span>'
        '<a class="sbtn" href="#">読む →</a></div>\n'
        + '<div class="searchbar">'
        '<input id="search" type="search" placeholder="タイトルで検索…" '
        'autocomplete="off">'
        '<span id="search-count" class="count"></span></div>\n'
        + '<p class="count">全 {n} 話 ・ 総 {c:,} 文字'
        ' ・ <a href="all.html">全話を続けて読む →</a></p>\n'.format(
            n=len(episodes), c=total_chars)
        + '<ul class="toc">\n'
        + "\n".join(rows)
        + "\n</ul>"
    )
    return page_html(SITE_TITLE, body, "index")


def build_empty_index() -> str:
    body = (
        "<h1>{site}</h1>\n".format(site=html.escape(SITE_TITLE))
        + '<p class="count">まだ原稿がありません。</p>\n'
        + "<p><code>episodes/</code> に <code>.txt</code> を置くか、"
        "<code>incoming/</code> に zip を置いて再ビルドしてください。</p>"
    )
    return page_html(SITE_TITLE, body, "index")


def _nav(prev_ep, next_ep) -> str:
    if prev_ep:
        prev = '<a data-nav-prev href="{}.html">← 前の話</a>'.format(
            html.escape(prev_ep["id"]))
    else:
        prev = '<span class="disabled">← 前の話</span>'
    if next_ep:
        nxt = '<a data-nav-next href="{}.html">次の話 →</a>'.format(
            html.escape(next_ep["id"]))
    else:
        nxt = '<span class="disabled">次の話 →</span>'
    return (
        '<nav class="episode-nav">\n'
        "  {prev}\n"
        '  <a data-nav-toc href="index.html">目次</a>\n'
        "  {next}\n"
        "</nav>"
    ).format(prev=prev, next=nxt)


def build_episode(ep, prev_ep, next_ep) -> str:
    share_row = (
        '<div class="share-row">この話をシェア：'
        '<a data-share-x class="sbtn" role="button">X</a> '
        '<a data-share-line class="sbtn" role="button">LINE</a> '
        '<button data-share class="sbtn" type="button">リンクをコピー</button>'
        "</div>"
    )
    body = (
        "<h1>{title}</h1>\n".format(title=html.escape(ep["title"]))
        + '<p class="ep-meta">{chars:,}字・約{mins}分で読めます</p>\n'.format(
            chars=ep["chars"], mins=ep["mins"])
        + "<article>\n{content}\n</article>\n".format(content=ep["body_html"])
        + _nav(prev_ep, next_ep) + "\n"
        + share_row
    )
    attrs = 'data-ep="{id}" data-title="{title}"'.format(
        id=html.escape(ep["id"]), title=html.escape(ep["title"]))
    return page_html(ep["title"], body, "episode", attrs)


def build_all(episodes) -> str:
    mini = ['<nav class="all-toc"><b>目次</b><ul>']
    for ep in episodes:
        mini.append('<li><a href="#{id}">{title}</a></li>'.format(
            id=html.escape(ep["id"]), title=html.escape(ep["title"])))
    mini.append("</ul></nav>")

    sections = []
    for ep in episodes:
        sections.append(
            '<section class="ep" id="{id}">\n'
            "<h2>{title}</h2>\n"
            "<article>\n{content}\n</article>\n"
            '<p class="back"><a href="#top">▲ 目次へ</a></p>\n'
            "</section>".format(
                id=html.escape(ep["id"]),
                title=html.escape(ep["title"]),
                content=ep["body_html"],
            )
        )

    body = (
        '<h1 id="top">{site} ｜ 全話</h1>\n'.format(site=html.escape(SITE_TITLE))
        + "".join(mini) + "\n"
        + "\n".join(sections)
    )
    return page_html(SITE_TITLE + " ｜ 全話", body, "episode",
                     'data-ep="__all__" data-title="全話"')


# ──────────────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────────────
def main():
    extract_zips()

    txt_files = []
    if EPISODES_DIR.is_dir():
        txt_files = sorted(EPISODES_DIR.glob("*.txt"), key=sort_key)

    # public/ を作り直す
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True)
    (PUBLIC_DIR / "style.css").write_text(CSS, encoding="utf-8")
    (PUBLIC_DIR / "app.js").write_text(JS, encoding="utf-8")

    # 原稿がまだ無い場合は、空のプレースホルダーサイトを生成（CIを止めない）
    if not txt_files:
        print("原稿がありません。空のサイトを生成します。"
              " episodes/ に .txt を、または incoming/ に zip を置いてください。")
        (PUBLIC_DIR / "index.html").write_text(
            build_empty_index(), encoding="utf-8")
        return

    # 各話データ
    episodes = []
    used = set()
    total_chars = 0
    for i, path in enumerate(txt_files):
        title = path.stem
        sid = slugify(title, i)
        base, n = sid, 1
        while sid in used:
            sid = "{}_{}".format(base, n)
            n += 1
        used.add(sid)

        text = read_text(path)
        chars = count_chars(text)
        total_chars += chars
        episodes.append({
            "title": title,
            "id": sid,
            "chars": chars,
            "mins": reading_minutes(chars),
            "body_html": body_to_html(text),
        })

    # 出力
    (PUBLIC_DIR / "index.html").write_text(
        build_index(episodes, total_chars), encoding="utf-8")
    (PUBLIC_DIR / "all.html").write_text(
        build_all(episodes), encoding="utf-8")
    for i, ep in enumerate(episodes):
        prev_ep = episodes[i - 1] if i > 0 else None
        next_ep = episodes[i + 1] if i < len(episodes) - 1 else None
        (PUBLIC_DIR / (ep["id"] + ".html")).write_text(
            build_episode(ep, prev_ep, next_ep), encoding="utf-8")

    print("完了: {} 話・総 {:,} 文字 → {}/".format(
        len(episodes), total_chars, PUBLIC_DIR))
    for i, ep in enumerate(episodes, 1):
        print("  {:>3}. {}  ({}.html)".format(i, ep["title"], ep["id"]))


# ──────────────────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────────────────
CSS = """\
:root{
  --max-width:42rem;
  --user-scale:1;
  --bg:#fbfbf9; --fg:#1a1a1a; --muted:#6b6b6b; --link:#2b6cb0;
  --border:#e6e6e0; --card:#ffffff; --bar:#2b6cb0; --accent:#2b6cb0;
}
:root[data-theme="dark"]{
  --bg:#15171a; --fg:#e6e6e6; --muted:#9aa0a6; --link:#7db4ff;
  --border:#2c2f34; --card:#1e2126; --bar:#7db4ff; --accent:#7db4ff;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme]){
    --bg:#15171a; --fg:#e6e6e6; --muted:#9aa0a6; --link:#7db4ff;
    --border:#2c2f34; --card:#1e2126; --bar:#7db4ff; --accent:#7db4ff;
  }
}
*{box-sizing:border-box;}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;}
body{
  margin:0;background:var(--bg);color:var(--fg);
  font-family:"Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic UI",
    "Yu Gothic","Meiryo","Noto Sans JP",system-ui,sans-serif;
  font-size:calc(1.0625rem * var(--user-scale));
  line-height:1.9;letter-spacing:.02em;
  -webkit-font-smoothing:antialiased;
}
:root[data-font="serif"] body{
  font-family:"Hiragino Mincho ProN","Yu Mincho","YuMincho",
    "Noto Serif JP","Times New Roman",serif;
}
a{color:var(--link);text-decoration:none;}
a:hover{text-decoration:underline;}

/* ツールバー */
.toolbar{
  position:sticky;top:0;z-index:30;
  display:flex;align-items:center;justify-content:space-between;
  gap:.5rem;padding:.5rem .9rem;
  background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:saturate(150%) blur(8px);
  border-bottom:1px solid var(--border);
}
.toolbar .brand{color:var(--fg);font-weight:600;font-size:.95rem;}
.toolbar .tools{display:flex;gap:.4rem;position:relative;}
.tbtn{
  font:inherit;font-size:.85rem;cursor:pointer;
  background:var(--card);color:var(--fg);
  border:1px solid var(--border);border-radius:8px;padding:.35rem .6rem;
}
.tbtn:hover{border-color:var(--accent);}
.panel{
  position:absolute;right:0;top:calc(100% + .5rem);
  width:min(20rem,86vw);background:var(--card);
  border:1px solid var(--border);border-radius:12px;
  box-shadow:0 8px 30px rgba(0,0,0,.18);
  padding:.4rem .8rem;display:none;
}
.panel.open{display:block;}
.panel .row{
  display:flex;align-items:center;justify-content:space-between;gap:.6rem;
  padding:.6rem 0;border-bottom:1px solid var(--border);font-size:.9rem;
}
.panel .row:last-child{border-bottom:0;}
.panel .grp{display:flex;gap:.3rem;}
.sbtn{
  font:inherit;font-size:.82rem;cursor:pointer;
  background:var(--bg);color:var(--fg);
  border:1px solid var(--border);border-radius:7px;padding:.3rem .6rem;
  text-align:center;
}
.sbtn:hover{border-color:var(--accent);text-decoration:none;}

/* プログレスバー */
#progress{position:sticky;top:0;z-index:20;height:3px;background:transparent;}
#progress-bar{height:3px;width:0;background:var(--bar);transition:width .1s linear;}
:root[data-page="index"] #progress{display:none;}

.wrap{max-width:var(--max-width);margin:0 auto;padding:1.4rem 1.25rem 5rem;}

h1{font-size:1.5rem;line-height:1.5;margin:.6rem 0 1.4rem;
  padding-bottom:.7rem;border-bottom:2px solid var(--border);}
h2{font-size:1.25rem;margin:2.5rem 0 1.2rem;padding-bottom:.5rem;
  border-bottom:1px solid var(--border);}

/* 目次 */
.searchbar{display:flex;align-items:center;gap:.6rem;margin:.4rem 0 1rem;}
#search{
  flex:1;font:inherit;font-size:1rem;padding:.6rem .8rem;
  background:var(--card);color:var(--fg);
  border:1px solid var(--border);border-radius:10px;
}
.count{color:var(--muted);font-size:.9rem;}
.resume{
  display:flex;align-items:center;justify-content:space-between;gap:.6rem;
  background:var(--card);border:1px solid var(--accent);border-radius:10px;
  padding:.7rem .9rem;margin:0 0 1rem;font-size:.92rem;
}
.resume .p{color:var(--muted);}
ul.toc{list-style:none;margin:0;padding:0;}
ul.toc li{border-bottom:1px solid var(--border);}
ul.toc li a{
  display:flex;align-items:baseline;gap:.7rem;
  padding:.85rem .25rem;color:var(--fg);
}
ul.toc li a:hover{color:var(--link);text-decoration:none;}
ul.toc .num{
  flex:none;min-width:2.2rem;color:var(--muted);font-size:.85rem;
  font-variant-numeric:tabular-nums;text-align:right;
}
ul.toc .ti{flex:1;}
ul.toc .meta{flex:none;color:var(--muted);font-size:.78rem;white-space:nowrap;}
ul.toc li.read .ti::after{content:" ✓";color:var(--accent);font-size:.85em;}
ul.toc li.read{opacity:.72;}

/* 本文 */
.ep-meta{color:var(--muted);font-size:.85rem;margin:-.6rem 0 1.6rem;}
article p{margin:0;margin-block-end:1.25rem;text-indent:1em;}
article p.blank{margin-block-end:1rem;}

/* 縦書き */
:root[data-mode="vertical"] .wrap{max-width:none;}
:root[data-mode="vertical"] article{
  writing-mode:vertical-rl;text-orientation:mixed;
  height:calc(100dvh - 8.5rem);
  padding-block:.5rem;
}
:root[data-mode="vertical"] article p{text-indent:1em;}
:root[data-mode="vertical"] .ep-meta{writing-mode:horizontal-tb;}

/* ナビ */
nav.episode-nav{
  display:flex;justify-content:space-between;gap:.5rem;
  margin:2.5rem 0 0;padding-top:1.25rem;
  border-top:1px solid var(--border);font-size:.95rem;
}
nav.episode-nav a,nav.episode-nav span{
  flex:1;text-align:center;padding:.6rem .4rem;
  border:1px solid var(--border);border-radius:8px;background:var(--card);
}
nav.episode-nav span.disabled{color:#999;background:transparent;opacity:.5;}
nav.episode-nav a:hover{border-color:var(--accent);text-decoration:none;}

.share-row{
  margin:1.6rem 0 0;padding-top:1.2rem;border-top:1px dashed var(--border);
  font-size:.85rem;color:var(--muted);display:flex;align-items:center;
  gap:.5rem;flex-wrap:wrap;
}

/* 全話ページ */
.all-toc{
  background:var(--card);border:1px solid var(--border);border-radius:10px;
  padding:.6rem 1rem 1rem;margin:0 0 2rem;
}
.all-toc ul{list-style:none;margin:.4rem 0 0;padding:0;
  columns:2;column-gap:1.5rem;font-size:.92rem;}
.all-toc li{margin:.25rem 0;break-inside:avoid;}
.ep .back{margin-top:1.5rem;font-size:.85rem;}

/* トップへ */
#to-top{
  position:fixed;right:1rem;bottom:1rem;z-index:25;
  width:2.8rem;height:2.8rem;border-radius:50%;cursor:pointer;
  background:var(--accent);color:#fff;border:0;font-size:1.2rem;
  opacity:0;pointer-events:none;transition:opacity .2s;
  box-shadow:0 4px 14px rgba(0,0,0,.25);
}
#to-top.show{opacity:.9;pointer-events:auto;}
#to-top:hover{opacity:1;}

/* トースト */
.toast{
  position:fixed;left:50%;bottom:1.5rem;transform:translate(-50%,1rem);
  background:#222;color:#fff;padding:.6rem 1.1rem;border-radius:999px;
  font-size:.85rem;opacity:0;transition:all .3s;z-index:50;pointer-events:none;
}
.toast.show{opacity:.95;transform:translate(-50%,0);}

@media (max-width:480px){
  body{line-height:1.85;}
  .wrap{padding:1rem 1rem 4rem;}
  nav.episode-nav{font-size:.85rem;}
  .all-toc ul{columns:1;}
  ul.toc .meta{display:none;}
}
@media print{
  .toolbar,#progress,#to-top,.share-row,nav.episode-nav,.searchbar,.resume{display:none!important;}
}
"""

# ──────────────────────────────────────────────────────────────────────────
# JavaScript
# ──────────────────────────────────────────────────────────────────────────
JS = """\
(function(){
  var root=document.documentElement;
  var page=root.dataset.page;
  if('scrollRestoration' in history){ history.scrollRestoration='manual'; }

  function get(k,d){ try{ var v=localStorage.getItem(k); return v===null?d:v; }catch(e){ return d; } }
  function set(k,v){ try{ localStorage.setItem(k,v); }catch(e){} }
  function $(s){ return document.querySelector(s); }
  function readSet(){ try{ return JSON.parse(get('read','{}'))||{}; }catch(e){ return {}; } }

  /* ---- 表示設定 ---- */
  var scale=parseFloat(get('fscale','1'))||1;
  function applyScale(){ scale=Math.min(1.8,Math.max(0.8,Math.round(scale*100)/100));
    root.style.setProperty('--user-scale',scale); set('fscale',String(scale)); onScroll(); }

  function setTheme(t){ if(t){root.dataset.theme=t;} else {delete root.dataset.theme;} set('theme',t||''); upTheme(); }
  function upTheme(){ var b=$('#btn-theme'); if(b) b.textContent=(root.dataset.theme==='dark')?'☀ ライト':'\U0001F319 ダーク'; }
  function setFont(f){ if(f==='serif'){root.dataset.font='serif';} else {delete root.dataset.font;} set('font',f==='serif'?'serif':''); upFont(); }
  function upFont(){ var b=$('#btn-font'); if(b) b.textContent=(root.dataset.font==='serif')?'明朝':'ゴシック'; }
  function setMode(m){ if(m==='vertical'){root.dataset.mode='vertical';} else {delete root.dataset.mode;} set('mode',m==='vertical'?'vertical':''); upMode(); restoreScroll(); onScroll(); }
  function upMode(){ var b=$('#btn-mode'); if(b) b.textContent=(root.dataset.mode==='vertical')?'横書き':'縦書き'; }

  var bt=$('#btn-theme'); if(bt) bt.addEventListener('click',function(){ setTheme(root.dataset.theme==='dark'?'light':'dark'); }); upTheme();
  var bf=$('#btn-font'); if(bf) bf.addEventListener('click',function(){ setFont(root.dataset.font==='serif'?'sans':'serif'); }); upFont();
  var bm=$('#btn-mode'); if(bm) bm.addEventListener('click',function(){ setMode(root.dataset.mode==='vertical'?'horizontal':'vertical'); }); upMode();
  var fp=$('#btn-fontplus'); if(fp) fp.addEventListener('click',function(){ scale+=0.1; applyScale(); });
  var fm=$('#btn-fontminus'); if(fm) fm.addEventListener('click',function(){ scale-=0.1; applyScale(); });
  var fr=$('#btn-fontreset'); if(fr) fr.addEventListener('click',function(){ scale=1; applyScale(); });

  var gear=$('#btn-settings'), panel=$('#settings-panel');
  if(gear&&panel){
    gear.addEventListener('click',function(e){ e.stopPropagation(); panel.classList.toggle('open'); });
    document.addEventListener('click',function(e){ if(panel.classList.contains('open')&&!panel.contains(e.target)&&e.target!==gear) panel.classList.remove('open'); });
  }

  /* ---- 共有 ---- */
  function toast(msg){ var t=document.createElement('div'); t.className='toast'; t.textContent=msg;
    document.body.appendChild(t); setTimeout(function(){t.classList.add('show');},10);
    setTimeout(function(){ t.classList.remove('show'); setTimeout(function(){t.remove();},300); },1800); }
  function share(){
    var data={ title:document.title, url:location.href };
    if(navigator.share){ navigator.share(data).catch(function(){}); return; }
    if(navigator.clipboard&&navigator.clipboard.writeText){
      navigator.clipboard.writeText(location.href).then(function(){ toast('リンクをコピーしました'); },
        function(){ window.prompt('URLをコピーしてください', location.href); });
    } else { window.prompt('URLをコピーしてください', location.href); }
  }
  [].forEach.call(document.querySelectorAll('[data-share]'),function(b){ b.addEventListener('click',share); });
  [].forEach.call(document.querySelectorAll('[data-share-x]'),function(a){
    a.href='https://twitter.com/intent/tweet?text='+encodeURIComponent(document.title)+'&url='+encodeURIComponent(location.href);
    a.target='_blank'; a.rel='noopener'; });
  [].forEach.call(document.querySelectorAll('[data-share-line]'),function(a){
    a.href='https://social-plugins.line.me/lineit/share?url='+encodeURIComponent(location.href);
    a.target='_blank'; a.rel='noopener'; });

  /* ---- トップへ ---- */
  var toTop=$('#to-top');
  if(toTop){ toTop.addEventListener('click',function(){ window.scrollTo({top:0,left:0,behavior:'smooth'}); }); }

  /* ---- プログレス / しおり / 既読 ---- */
  var epId=document.body.getAttribute('data-ep')||'';
  function metrics(){
    var vertical=root.dataset.mode==='vertical';
    var el=document.scrollingElement||document.documentElement;
    var pos,max;
    if(vertical){ pos=Math.abs(window.scrollX); max=el.scrollWidth-el.clientWidth; }
    else { pos=window.scrollY; max=el.scrollHeight-el.clientHeight; }
    return { frac: max>0?Math.min(1,pos/max):0, x:window.scrollX, y:window.scrollY };
  }
  var bar=$('#progress-bar');
  function onScroll(){
    var m=metrics();
    if(bar) bar.style.width=(m.frac*100)+'%';
    if(toTop){ if(Math.abs(m.y)>400||Math.abs(m.x)>400) toTop.classList.add('show'); else toTop.classList.remove('show'); }
    if(epId && page==='episode'){
      set('pos:'+epId, JSON.stringify({x:m.x,y:m.y}));
      set('last', JSON.stringify({ id:epId, title:document.body.getAttribute('data-title')||document.title, frac:m.frac }));
      if(m.frac>0.9 && epId!=='__all__'){ var r=readSet(); if(!r[epId]){ r[epId]=1; set('read',JSON.stringify(r)); } }
    }
  }
  function restoreScroll(){
    if(!epId) return;
    var p; try{ p=JSON.parse(get('pos:'+epId,'')); }catch(e){ p=null; }
    if(p){ requestAnimationFrame(function(){ window.scrollTo(p.x||0,p.y||0); onScroll(); }); }
  }

  applyScale();

  if(page==='episode'){
    window.addEventListener('scroll',onScroll,{passive:true});
    window.addEventListener('resize',onScroll);
    restoreScroll(); onScroll();
    document.addEventListener('keydown',function(e){
      if(e.target&&/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
      if(e.metaKey||e.ctrlKey||e.altKey) return;
      var prev=document.querySelector('[data-nav-prev]'),
          next=document.querySelector('[data-nav-next]'),
          toc=document.querySelector('[data-nav-toc]');
      if(e.key==='ArrowLeft'&&prev){ location.href=prev.href; }
      else if(e.key==='ArrowRight'&&next){ location.href=next.href; }
      else if((e.key==='t'||e.key==='Escape')&&toc){ location.href=toc.href; }
    });
  } else {
    window.addEventListener('scroll',onScroll,{passive:true});
    onScroll();
  }

  /* ---- 目次ページ ---- */
  if(page==='index'){
    var box=$('#search');
    var items=[].slice.call(document.querySelectorAll('.toc li'));
    if(box){
      box.addEventListener('input',function(){
        var q=box.value.trim().toLowerCase(), n=0;
        items.forEach(function(li){
          var t=(li.getAttribute('data-title')||'').toLowerCase();
          var hit=!q||t.indexOf(q)>=0;
          li.style.display=hit?'':'none'; if(hit) n++;
        });
        var c=$('#search-count'); if(c) c.textContent=q?(n+' 件'):'';
      });
    }
    var r=readSet();
    items.forEach(function(li){ if(r[li.getAttribute('data-id')]) li.classList.add('read'); });
    var last; try{ last=JSON.parse(get('last','')); }catch(e){ last=null; }
    var rb=$('#resume');
    if(rb&&last&&last.id&&last.id!=='__all__'){
      rb.querySelector('a').href=last.id+'.html';
      rb.querySelector('.t').textContent=last.title||'';
      rb.querySelector('.p').textContent=Math.round((last.frac||0)*100)+'%';
      rb.style.display='';
    }
  }
})();
"""


if __name__ == "__main__":
    main()
