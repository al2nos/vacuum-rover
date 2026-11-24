#!/usr/bin/env python3
"""Генератор сайта vacuum-rover: docs/*.md (GitHub) -> статические страницы.

Использование: python3 deploy/build_site.py <каталог_с_md> <каталог_вывода>

Сайт https://3dlb.ru — зеркало базы знаний репозитория. Канонический
источник — docs/ в GitHub; сайт пересобирается после изменения документов.
Агент с доступом к VDS: сгенерируй страницы и перезалей в /var/www/rover/.
Требуется: pandoc.

Вёрстка — альбомная: широкая колонка (до 1380 px), текст в колонке
~820 px, таблицы и код на всю ширину, списки в две колонки на широком
экране, индекс KB — сетка карточек.
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
  /* альбомная вёрстка: широкая колонка, контент занимает экран по горизонтали */
  .wrap{max-width:1380px;margin:0 auto;padding:0 28px}
  header{border-bottom:1px solid var(--line);padding:16px 0;margin-bottom:32px}
  .logo{font-weight:700;text-decoration:none;color:var(--text)}
  .logo span{color:var(--accent)}
  nav a{color:var(--dim);text-decoration:none;margin-left:18px;font-size:14px}
  nav a:hover{color:var(--text)}
  article{padding-bottom:64px}
  /* в альбомной ориентации текст — в удобной колонке ~70 символов,
     а таблицы, код и широкие блоки растягиваются на весь экран */
  article p,article blockquote{max-width:820px}
  h1{font-size:30px;margin-bottom:20px}
  h2{font-size:20px;margin:32px 0 12px;padding-top:16px;border-top:1px solid var(--line)}
  p,li{color:#c9d1d9;font-size:15px}
  ul,ol{padding-left:24px;margin:8px 0}
  /* длинные списки — в две колонки на широком экране */
  @media(min-width:1000px){
    article ul{columns:2;column-gap:44px}
    article li{break-inside:avoid}
  }
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
  .status-banner{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--orange);border-radius:8px;padding:14px 18px;margin-bottom:28px;font-size:14px;max-width:none}
  .status-banner b{color:var(--orange)}
  footer{border-top:1px solid var(--line);padding:24px 0;color:var(--dim);font-size:13px}
  input[type="checkbox"]{accent-color:var(--green);margin-right:8px}
  /* сетка карточек (индекс базы знаний) */
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin:16px 0}
  .grid a{display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;text-decoration:none;color:var(--text);font-size:15px}
  .grid a:hover{border-color:var(--accent)}
  .grid a small{display:block;color:var(--dim);font-size:12px;margin-top:4px}
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
    "protocol": "Протокол обмена",
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
    # индекс KB — сетка карточек
    descr = {
        "architecture": "Состав ровера: узлы, сети, роли одноплатников",
        "donors": "Разбор доноров: STYTJ02YM и C103, что берём",
        "lidars": "Delta-2C PRO и Delta-2A: распиновка, протоколы, декодеры",
        "vision": "Стереокамеры и обработка на Tinker Board 2",
        "power": "Питание: батареи пылесосов, BTS7960, безопасность",
        "frame-print": "Рама и 3D-печать: PETG, модульность, AD5X",
        "protocol": "MQTT: топики, форматы, сканы лидара, пульт",
    }
    cards = '<div class="grid">' + "\n".join(
        f'<a href="/kb/{s}.html">{t}<small>{descr.get(s, "")}</small></a>'
        for s, t in PAGES.items()) + "</div>"
    (kb / "index.html").write_text(
        TEMPLATE.replace("$body$", f"<h1>База знаний</h1>{cards}")
                .replace("$title$", "База знаний"),
        encoding="utf-8")
    print(f"  {kb / 'index.html'}")


if __name__ == "__main__":
    main()
