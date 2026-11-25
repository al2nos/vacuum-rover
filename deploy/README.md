# deploy/ — сборка сайта и выкладка

Сайт `https://3dlb.ru` — зеркало репозитория. Канон — `docs/*.md` в `main`,
сайт пересобирается после изменения документов. Генератор один:
`deploy/build_site.py`.

## Что генерируется

| Файл | Источник |
|---|---|
| `index.html` (лендинг) | `deploy/site.json` (hero, компоненты, сеть, статус) |
| `dashboard/index.html` | `deploy/site.json` (`nodes`, `status`) |
| `kb/<slug>.html` | `docs/<slug>.md` — список страниц в `site.json` → `kb` |
| `kb/index.html` | `site.json` → `kb` |
| `stages/index.html` | `docs/roadmap.md` + баннер статуса из `site.json` |
| `robots.txt` | закрывает индексацию (сайт под логином) |

Лендинг и дашборд раньше правились руками прямо на VDS и дрейфовали от
`docs/`. Теперь их данные лежат в `deploy/site.json` и меняются через PR.

## Сборка

Нужен `pandoc` (≥ 2.x) и Python 3.

```sh
python3 deploy/build_site.py docs dist
```

Проверка локально:

```sh
python3 -m http.server 8000 -d dist
# http://127.0.0.1:8000/
```

`dist/` — черновик, в репозиторий не коммитится.

## Выкладка на VDS

Файлы сайта лежат в `/var/www/rover/` (nginx, basic auth). Раскладка
`dist/` повторяет её: `index.html`, `dashboard/`, `kb/`, `stages/`,
`robots.txt`.

```sh
python3 deploy/build_site.py docs dist
rsync -a dist/ root@3dlb.ru:/var/www/rover/
```

`--delete` не используем: в `/var/www/rover/` могут быть файлы, которые
генерирует не этот скрипт (статика, сертификаты Let's Encrypt).

Агент без доступа к VDS после правки `docs/` ставит в `STATE.md`
пометку `site-sync: pending`.

## Узел ровера (Тинкер): лидар + агент

`deploy/node-agent/` — то, что ставится на борт:

| Файл | Назначение |
|---|---|
| `lidar_delta.py` | декодер Delta-2A/2C: `/dev/ttyS0` → `/run/rover/scan.json` |
| `agent.py` | MQTT: телеметрия системы + поток сканов + статистика лидара |
| `rover-lidar.service`, `rover-agent.service` | systemd-юниты |

Установка (root на узле):

```sh
mkdir -p /opt/rover-agent /etc/rover /run/rover
install -m644 lidar_delta.py agent.py /opt/rover-agent/
install -m600 agent.env /etc/rover/agent.env   # ROVER_NODE/BROKER/USER/PASS
apt install -y python3.14-venv                 # ensurepip в Armbian отсутствует
python3 -m venv /opt/rover-agent/venv
/opt/rover-agent/venv/bin/pip install 'paho-mqtt>=1.6' psutil
install -m644 rover-lidar.service rover-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now rover-lidar rover-agent
```

`agent.env` (не в репозитории):

```
ROVER_NODE=tinker
ROVER_BROKER=10.77.0.1
ROVER_MQTT_USER=tinker
ROVER_MQTT_PASS=<из mosquitto_passwd на VDS>
ROVER_SCAN_FILE=/run/rover/scan.json
ROVER_LIDAR_STATS=/run/rover/lidar_stats.json
```

Проверка: `cat /run/rover/lidar_stats.json` (растёт `frames_meas`),
`journalctl -u rover-lidar -f`, затем `/api/nodes` консоли.

`ExecStartPre` в `rover-lidar.service` переинициализирует UART0: если пины
трогали через gpiolib, драйвер остаётся в режиме GPIO и байты не приходят.


## Требования к nginx (сниппет)

Применяется владельцем или агентом с доступом к VDS. Точные пути к
`auth_basic_user_file` и сертификатам — по `nginx -T` на VDS
(`TODO(needs-vds)`), ниже — форма, а не копипаста целиком.

```nginx
# HTTP → HTTPS
server {
    listen 80;
    server_name 3dlb.ru;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name 3dlb.ru;

    ssl_certificate     /etc/letsencrypt/live/3dlb.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/3dlb.ru/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000" always;

    root /var/www/rover;

    auth_basic           "vacuum-rover";
    auth_basic_user_file /etc/nginx/.htpasswd-rover;

    location / {
        try_files $uri $uri/ =404;
    }

    # пульт: FastAPI на 127.0.0.1:8080, включая WebSocket
    location /console/ {
        proxy_pass http://127.0.0.1:8080/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    # этап 3: rosbridge на Тинкере через WireGuard
    # location /rosbridge/ {
    #     proxy_pass http://10.77.0.11:9090/;
    #     proxy_http_version 1.1;
    #     proxy_set_header Upgrade $http_upgrade;
    #     proxy_set_header Connection "upgrade";
    # }
}
```

Замечания по безопасности (из аудита 2026-11-25):

- редирект HTTP→HTTPS на VDS уже настроен (nginx 1.26.3, отдельный
  server на :80), HSTS не отдаётся — достаточно добавить `add_header`
  из сниппета выше;
- сайт целиком под одним общим basic-auth логином; пароль стоит
  ротировать после любого попадания в чат/лог.
