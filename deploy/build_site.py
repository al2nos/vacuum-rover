#!/usr/bin/env python3
"""Генератор сайта vacuum-rover: docs/*.md (GitHub) -> статические страницы.

Использование: python3 deploy/build_site.py <каталог_с_md> <каталог_вывода>

Сайт https://3dlb.ru — зеркало базы знаний репозитория. Канонический
источник — docs/ в GitHub; сайт пересобирается после изменения документов.
Агент с доступом к VDS: сгенерируй страницы и перезалей в /var/www/rover/.
Требуется: pandoc.
"""
import pathlib
import subprocess
import sys

TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>$title$ — vacuum-rover</title>
<style>
  :root{
    --bg:#0d1117; --panel:#161b22; --line:#21262d; --text:#e6edf3;
    --dim:#8b949e; --accent:#58a6ff; --green:#3fb950; --orange:#d29922;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.65}
  .wrap{max-width:860px;margin:0 auto;padding:0 20px}
  header{border-bottom:1px solid var(--line);padding:16px 0;margin-bottom:32px}
  .logo{font-weight:700;text-decoration:none;color:var(--text)}
  .logo span{color:var(--accent)}
  nav a{color:var(--dim);text-decoration:none;margin-left:18px;font-size:14px}
  nav a:hover{color:var(--text)}
  article{padding-bottom:64px}
  h1{font-size:30px;margin-bottom:20px}
  h2{font-size:20px;margin:32px 0 12px;padding-top:16px;border-top:1px solid var(--line)}
  p,li{color:#c9d1d9;font-size:15px}
  ul,ol{padding-left:24px;margin:8px 0}
  li{margin:4px 0}
  a{color:var(--accent)}
  code{background:#010409;border:1px solid var(--line);border-radius:5px;padding:1px 6px;font-size:13px;color:#a5d6ff}
  pre{background:#010409;border:1px solid var(--line);border-radius:8px;padding:14px;overflow-x:auto;margin:12px 0}
  pre code{background:none;border:none;padding:0}
  table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}
  th,td{border:1px solid var(--line);padding:8px 12px;text-align:left}
  th{background:var(--panel)}
  blockquote{border-left:3px solid var(--accent);padding-left:14px;color:var(--dim);margin:12px 0}
  .crumb{color:var(--dim);font-size:13px;margin-bottom:16px}
  .crumb a{color:var(--dim)}
  .status-banner{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--orange);border-radius:8px;padding:14px 18px;margin-bottom:28px;font-size:14px}
  .status-banner b{color:var(--orange)}
  footer{border-top:1px solid var(--line);padding:24px 0;color:var(--dim);font-size:13px}
  input[type="checkbox"]{accent-color:var(--green);margin-right:8px}
</style>
</head>
<body>
<header><div class="wrap">
  <a class="logo" href="/">vacuum<span>-</span>rover</a>
  <nav style="float:right">
    <a href="/stages/">Этапы</a>
    <a href="/kb/">База знаний</a>
    <a href="/dashboard/">Дашборд</a>
  </nav>
</div></header>
<article><div class="wrap">
<div class="crumb"><a href="/kb/">База знаний</a> / $title$</div>
$body$
</div></article>
<footer><div class="wrap">vacuum-rover · зеркало репозитория · обновляется агентами при изменении docs/</div></footer>
</body>
</html>
"""

STAGES_TEMPLATE = TEMPLATE.replace(
    '<div class="crumb"><a href="/kb/">База знаний</a> / $title$</div>',
    '<div class="crumb"><a href="/stages/">Этапы</a></div>'
)

PAGES = {
    "architecture": "Архитектура",
    "donors": "Доноры",
    "lidars": "Лидары",
    "vision": "Стереозрение",
    "power": "Питание и электрика",
    "frame-print": "Рама и печать",
}


def render(md: pathlib.Path, out: pathlib.Path, title: str, template: str):
    body = subprocess.run(
        ["pandoc", "--from", "markdown+pipe_tables", "--to", "html", str(md)],
        capture_output=True, text=True, check=True,
    ).stdout
    html = template.replace("$body$", body).replace("$title$", title)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"  {out}")


def main():
    docs_dir = pathlib.Path(sys.argv[1])
    out_dir = pathlib.Path(sys.argv[2])
    kb = out_dir / "kb"
    print("KB:")
    for slug, title in PAGES.items():
        render(docs_dir / f"{slug}.md", kb / f"{slug}.html", title, TEMPLATE)
    print("Stages:")
    render(docs_dir / "roadmap.md", out_dir / "stages" / "index.html",
          "Дорожная карта", STAGES_TEMPLATE)
    cards = "\n".join(
        f'<p><a href="/kb/{s}.html">{t}</a></p>' for s, t in PAGES.items())
    (kb / "index.html").write_text(
        TEMPLATE.replace("$body$", f"<h1>База знаний</h1>{cards}")
                .replace("$title$", "База знаний"),
        encoding="utf-8")
    print(f"  {kb / 'index.html'}")


if __name__ == "__main__":
    main()
