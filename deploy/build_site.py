#!/usr/bin/env python3
"""Генератор сайта vacuum-rover: repo -> статические страницы.

Источники:
  docs/*.md        — канон базы знаний (kb/, stages/), GitHub = источник истины
  deploy/site.json — данные лендинга и дашборда (статус, узлы, карточки)

Использование:
  python3 deploy/build_site.py <каталог_с_docs> <каталог_вывода>

Сайт https://3dlb.ru — зеркало базы знаний репозитория, целиком под
basic auth. Пример выкладки и сниппет nginx — deploy/README.md.
Требуется: pandoc.

Генерируются: index.html (лендинг), dashboard/index.html, kb/*.html,
kb/index.html, stages/index.html, robots.txt. Вёрстка — альбомная:
широкая колонка (до 1380 px), текст в колонке ~820 px, таблицы и код
на всю ширину, списки в две колонки, индекс KB — сетка карточек.
"""
import html
import json
import os
import pathlib
import shutil
import subprocess
import sys

BASE = pathlib.Path(__file__).resolve().parent
SITE_JSON = BASE / "site.json"
PANDOC = os.environ.get("PANDOC") or shutil.which("pandoc") or "pandoc"

CSS = """
  :root{
    --bg:#0d1117; --panel:#161b22; --line:#21262d; --text:#e6edf3;
    --dim:#8b949e; --accent:#58a6ff; --green:#3fb950; --orange:#d29922;
  }
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI",Roboto,Arial,sans-serif;line-height:1.65}
  /* альбомная вёрстка: широкая колонка, контент занимает экран по горизонтали */
  .wrap{max-width:1380px;margin:0 auto;padding:0 28px}
  header{border-bottom:1px solid var(--line);padding:16px 0;margin-bottom:32px}
  .logo{font-weight:700;text-decoration:none;color:var(--text);font-size:16px}
  .logo span{color:var(--accent)}
  nav{float:right}
  nav a{color:var(--dim);text-decoration:none;margin-left:18px;font-size:14px}
  nav a:hover{color:var(--text)}
  nav a.on{color:var(--text)}
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
  pre{background:#010409;border:1px solid var(--line);border-radius:8px;padding:14px;overflow-x:auto;margin:12px 0;font-size:13px;color:#a5d6ff}
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
  footer a{color:var(--dim)}
  input[type="checkbox"]{accent-color:var(--green);margin-right:8px}
  /* сетка карточек (индекс базы знаний) */
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin:16px 0}
  .grid a{display:block;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;text-decoration:none;color:var(--text);font-size:15px}
  .grid a:hover{border-color:var(--accent)}
  .grid a small{display:block;color:var(--dim);font-size:12px;margin-top:4px}
  /* лендинг */
  .hero{padding:56px 0 40px;text-align:center}
  .hero h1{font-size:40px;margin-bottom:16px}
  .hero p{color:var(--dim);font-size:18px;max-width:680px;margin:0 auto 24px}
  .badge{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:6px 16px;font-size:13px;color:var(--dim);margin:0 4px}
  .badge b{color:var(--green);font-weight:600}
  section.block{padding:40px 0;border-top:1px solid var(--line)}
  section.block h2{margin-top:0;padding-top:0;border-top:none}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px}
  .card h3{font-size:16px;margin-bottom:8px}
  .card p{color:var(--dim);font-size:14px}
  .card .tag{display:inline-block;font-size:11px;color:var(--accent);border:1px solid var(--line);border-radius:4px;padding:2px 8px;margin-bottom:10px}
  .card .links{margin-top:12px;font-size:14px}
  .card .links a{display:inline-block;margin-right:16px}
  /* дашборд */
  .node h3{font-size:15px;margin-bottom:6px}
  .node .muted{color:var(--dim);font-size:13px}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:8px}
  .dot.wait{background:var(--orange)}
  .dot.off{background:var(--dim)}
"""

NAV = [
    ("/", "Проект"),
    ("/stages/", "Этапы"),
    ("/kb/", "База знаний"),
    ("/dashboard/", "Дашборд"),
    ("/console/", "Пульт"),
]


def esc(value):
    return html.escape(str(value), quote=True)


def load_site():
    with SITE_JSON.open(encoding="utf-8") as f:
        return json.load(f)


def nav_html(active):
    links = []
    for url, label in NAV:
        cls = ' class="on"' if url == active else ""
        links.append(f'<a href="{url}"{cls}>{label}</a>')
    return "\n    ".join(links)


def page(site, title, body, active):
    repo = site["repo"]
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)} — vacuum-rover</title>
<style>{CSS}</style>
</head>
<body>
<header><div class="wrap">
  <a class="logo" href="/">vacuum<span>-</span>rover</a>
  <nav>
    {nav_html(active)}
  </nav>
</div></header>
<main>
{body}
</main>
<footer><div class="wrap">
  vacuum-rover · код и документация: <a href="{esc(repo)}">al2nos/vacuum-rover</a> ·
  ведут сменяющиеся ИИ-агенты по правилам <a href="{esc(repo)}/blob/main/AGENTS.md">AGENTS.md</a>
</div></footer>
</body>
</html>
"""


def render_markdown(md_path):
    try:
        result = subprocess.run(
            [PANDOC, "--from", "markdown+pipe_tables", "--to", "html",
             str(md_path)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=True,
        )
    except FileNotFoundError:
        sys.exit("pandoc не найден: установите pandoc или добавьте его в PATH")
    return result.stdout


def status_banner(site):
    st = site["status"]
    return (f'<div class="status-banner">Статус: <b>{esc(st["stage"])}</b> — '
            f'{esc(st["title"])} · {esc(st["detail"])}</div>')


def render_landing(site):
    hero = site["hero"]
    st = site["status"]
    badges = [f'<span class="badge">Статус: <b>{esc(st["stage"])}</b> — {esc(st["title"])}</span>']
    badges += [f'<span class="badge">{esc(b)}</span>' for b in site.get("badges", [])]

    cards = []
    for c in site["components"]:
        cards.append(f"""      <div class="card">
        <span class="tag">{esc(c["tag"])}</span>
        <h3>{esc(c["title"])}</h3>
        <p>{esc(c["text"])}</p>
      </div>""")
    components = "\n".join(cards)

    arch = esc("\n".join(site["arch"]))

    net = []
    for c in site.get("net_cards", []):
        links = []
        for key in ("link", "link2"):
            if c.get(key):
                links.append(f'<a href="{esc(c[key]["url"])}">{esc(c[key]["label"])}</a>')
        links_html = f'\n        <div class="links">{" ".join(links)}</div>' if links else ""
        net.append(f"""      <div class="card">
        <h3>{esc(c["title"])}</h3>
        <p>{esc(c["text"])}</p>{links_html}
      </div>""")
    net = "\n".join(net)

    body = f"""<div class="wrap">
  <div class="hero">
    <h1>{esc(hero["title"])}</h1>
    <p>{esc(hero["lead"])}</p>
    {" ".join(badges)}
  </div>

  <section class="block" id="about">
    <h2>Из чего собран</h2>
    <div class="cards">
{components}
    </div>
  </section>

  <section class="block" id="arch">
    <h2>Архитектура</h2>
    <pre>{arch}</pre>
    <p><a href="/kb/architecture.html">Подробнее об архитектуре</a></p>
  </section>

  <section class="block" id="net">
    <h2>Сеть 10.77.0.0/24</h2>
    <div class="cards">
{net}
    </div>
  </section>
</div>"""
    return page(site, "4WD ровер из роботов-пылесосов", body, "/")


def render_dashboard(site):
    cards = []
    for n in site["nodes"]:
        dot_cls = {"online": "", "waiting": " wait", "paused": " off"}.get(n["state"], " off")
        cards.append(f"""      <div class="card node">
        <h3><span class="dot{dot_cls}"></span>{esc(n["name"])}</h3>
        <p class="muted">{esc(n["ip"])} · {esc(n["role"])}<br>{esc(n["note"])}</p>
      </div>""")
    cards = "\n".join(cards)
    body = f"""<div class="wrap">
  <div class="crumb"><a href="/">Проект</a> / Дашборд</div>
  {status_banner(site)}
  <h1>Дашборд флотилии</h1>
  <p style="color:var(--dim);margin-bottom:28px">vacuum-rover · сеть 10.77.0.0/24 · сводка обновляется вместе с docs/</p>
  <div class="cards">
{cards}
  </div>
  <p style="color:var(--dim);font-size:13px;margin-top:32px">Живая телеметрия, карта лидара и управление — в
  <a href="/console/">пульте</a>. Эта страница — статическая сводка по узлам.</p>
</div>"""
    return page(site, "Дашборд", body, "/dashboard/")


def render_kb_page(site, docs_dir, out_dir, slug, title, descr):
    md = docs_dir / f"{slug}.md"
    if not md.exists():
        sys.exit(f"нет файла {md} для страницы «{title}»")
    body = f"""<article><div class="wrap">
<div class="crumb"><a href="/kb/">База знаний</a> / {esc(title)}</div>
{render_markdown(md)}
</div></article>"""
    out = out_dir / "kb" / f"{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(site, title, body, "/kb/"), encoding="utf-8")
    print(f"  {out}")


def render_kb_index(site, out_dir):
    cards = "\n".join(
        f'<a href="/kb/{esc(p["slug"])}.html">{esc(p["title"])}'
        f'<small>{esc(p["descr"])}</small></a>' for p in site["kb"])
    body = f"""<article><div class="wrap">
<div class="crumb"><a href="/kb/">База знаний</a></div>
<h1>База знаний</h1>
<div class="grid">
{cards}
</div>
</div></article>"""
    out = out_dir / "kb" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(site, "База знаний", body, "/kb/"), encoding="utf-8")
    print(f"  {out}")


def render_stages(site, docs_dir, out_dir):
    md = docs_dir / "roadmap.md"
    if not md.exists():
        sys.exit(f"нет файла {md}")
    body = f"""<article><div class="wrap">
<div class="crumb"><a href="/stages/">Этапы</a></div>
{status_banner(site)}
{render_markdown(md)}
</div></article>"""
    out = out_dir / "stages" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(site, "Дорожная карта", body, "/stages/"), encoding="utf-8")
    print(f"  {out}")


def render_robots(out_dir):
    out = out_dir / "robots.txt"
    out.write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    print(f"  {out}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 3:
        sys.exit("использование: build_site.py <каталог_с_docs> <каталог_вывода>")
    docs_dir = pathlib.Path(sys.argv[1])
    out_dir = pathlib.Path(sys.argv[2])
    site = load_site()

    print("Landing:")
    out = out_dir / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_landing(site), encoding="utf-8")
    print(f"  {out}")

    print("Dashboard:")
    out = out_dir / "dashboard" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_dashboard(site), encoding="utf-8")
    print(f"  {out}")

    print("KB:")
    for entry in site["kb"]:
        render_kb_page(site, docs_dir, out_dir, entry["slug"],
                       entry["title"], entry["descr"])
    render_kb_index(site, out_dir)

    print("Stages:")
    render_stages(site, docs_dir, out_dir)

    print("Extra:")
    render_robots(out_dir)


if __name__ == "__main__":
    main()
