# Дорожная карта и задачи

## Этап 0 — первый лидар (Delta-2C PRO) до полного успеха

Критерий успеха: стабильный LaserScan в RViz/визуализаторе, крутящаяся
башенка, данные без пропусков пакетов. Только потом второй лидар.

1. [x] Снять модуль с пылесоса C103, сфотографировать разъём и плату
      (нужна распиновка 5 пинов) — человек
2. [x] Стендовое питание: 5 В на модуль, 2.5–3.3 В на мотор
      (временно: 2×AA-батарейки = 3.0 В, потом крошечный buck)
3. [ ] Замер уровня TX мультиметром (3.3 или 5 В → нужен ли делитель
      перед RX Tinker Board 2) — человек
4. [x] Подключение к Tinker Board 2: TX → RX UART, GND, питание с шины
5. [x] Порт декодера протокола 0x11/0x13 (Python, по мотивам kaiaai/LDS
      и delta_2a_pi.py) — можно писать без железа на эмуляторе пакетов.
      Писать сразу в форме ROS-ноды (rclpy → sensor_msgs/LaserScan),
      публикация в MQTT-консоль делается параллельно тем же сканом
6. [x] Визуализация скана: простейший polar-plot / RViz2 / пульт
7. [x] Публикация sensor_msgs/LaserScan через rclpy (нода `rover_lidar`, `/scan`)
8. [ ] Разбор полётов: частота потерь пакетов, стабильность оборотов

## Этап 1 — второй лидар (Delta-2C PRO, 360°)

Второй такой же Delta-2C PRO, свободный UART на 40-pin, TX = 3.3 В
(замер владельца). Критерий: оба скана одновременно в пульте и RViz,
360° обзор.

1. [x] Включить UART4 на 40-pin: pin 19 = TXD, pin 21 = RXD (GPIO1_B0/A7),
       3.3 В; `overlays=uart4` в `/boot/armbianEnv.txt` → `/dev/ttyS4`
2. [x] Второй экземпляр декодера: `rover-lidar2.service`
       (`ROVER_LIDAR_DEV=/dev/ttyS4`, `/run/rover/scan2.json`,
       `lidar2_stats.json`)
3. [x] Агент: `ROVER_LIDAR_EXTRA` → `telemetry/lidar2`
4. [x] ROS 2: `/scan2` (`frame_id=lidar2`) через `rover_lidar2_ros.service`
5. [x] Пульт: оба скана на карте разными цветами, частоты по каждому лидару
6. [ ] Физическая установка башни и замер смещения/поворота лидара №2 —
       человек (без замера TF `base_link→lidar2` остаётся identity)
7. [ ] Слияние `/scan` + `/scan2` в costmap Nav2 / SLAM после замера TF

## Этап 2 — шасси и привод

- [ ] Замеры колёсных модулей ×4 (человек) → CAD адаптеров → печать
- [ ] Схема распиновки колёс → драйвер моторов на Tinker Board 2
- [ ] Электрика: батарея → выключатель → BTS7960 + buck 5 В
- [ ] Первый выезд: телеуправление (MQTT-пульт уже готов, см. ниже)

## Этап 3 — ROS 2 Lyrical + Nav2 (автономия)

Стек навигации — только бортовой, на Tinker Board 2. VDS его не
крутит (380 МБ RAM) — сайт общается с ровером через мост MQTT и
rosbridge.

Факт: образ Ubuntu 26.04 (resolute), поэтому стоит **ROS 2 Lyrical**,
а не Jazzy (решение D18). Тинкер — 6 ядер / 1.9 ГБ RAM.

1. [x] ROS 2 Lyrical из apt (arm64) на текущем образе Ubuntu 26.04
2. [x] Пакеты: ros-lyrical-ros-base, navigation2, slam-toolbox,
       rosbridge-suite, nav2-bringup
3. [ ] Дожим 2 ГБ RAM: zram/swap, ROS_LOCALHOST_ONLY=1, CycloneDDS
       (сейчас ~57 % RAM занято при работающем Nav2)
4. [x] Драйвер лидара как ROS-нода: `/run/rover/scan.json` → `/scan`
       (360 лучей, ~5–6 Гц; publication stamp из скана)
5. [ ] Base controller: /cmd_vel (Twist) → GPIO/PWM BTS7960, watchdog
       0.5 с. Приоритет: автономка > MQTT-телеоп (cmd_vel перекрывает)
6. [x] TF-каркас `map→odom→base_link→{lidar, base_footprint}`
       (`rover_tf`); смещения лидара — identity до замеров башни
7. [x] slam_toolbox онлайн-карта → `/map` → `telemetry/map`
       (компактно: только занятые ячейки)
8. [x] VDS: nginx /rosbridge/ → ws://10.77.0.11:9090 (Upgrade → 101)
9. [ ] Консоль: вкладка «Навигация»: клик по карте → цель Nav2,
       `/plan`, состояния lifecycle; сейчас — карта/поза/логи/телеоп
10. [ ] Прогоны: автономная езда по квартире, сбор проблем

Риск: Nav2 + SLAM + декодер на 2 ГБ — впритык. План Б: Nav2 перенести
на Zero 2 W (4 ГБ, слабее CPU — Nav2 ок, SLAM тяжелее), Тинкер оставить
на лидарах и стерео.

## Инфраструктура (готово, сессия 2026-11-24)

- [x] VDS 3dlb.ru: WireGuard-хаб 10.77.0.0/24, сайт под basic auth,
      peers tinker→10.77.0.11, opi3→10.77.0.12 (/usr/local/bin/make-peer.sh)
- [x] Сайт-зеркало базы знаний: /kb/ + /stages/, генератор
      deploy/build_site.py, альбомная вёрстка, ссылка на пульт в меню
- [x] Лендинг и дашборд генерируются из deploy/site.json, /kb/state.html,
      robots.txt, единая шапка/футер (issue #1, 2026-11-25)
- [x] rover-console (/console/): MQTT → FastAPI+SQLite → WebSocket,
      карточки узлов, графики по каждому датчику (30 мин + live),
      карта лидара (canvas, затухающий след), активность датчиков,
      джойстик teleop, редактор конфигурации (retained config/set)
- [x] node-agent (deploy/node-agent/): телеметрия 1 Гц + LWT + проброс
      сканов из $ROVER_SCAN_FILE в telemetry/lidar
- [x] Протокол docs/protocol.md: топики, формат сканов {start,step,r},
      границы MQTT/ROS 2/rosbridge
- [x] Проверка end-to-end эмулятором (fake_publisher): сканы → карта,
      метрики → графики, LWT → online/offline

## Этап 4 — второй модуль Orange Pi 3 LTS (подготовка, 2026-11-27)

Второй вычислитель в флоте для второго лидара/шлюза (см. `deploy/site.json`,
`docs/architecture.md`).

1. [x] Юнит `deploy/node-agent/rover-lidar-opos3.service` — декодер на OP3
       (UART → `/run/rover/scan2.json`) → agent → `telemetry/lidar2`
2. [ ] Подготовка железа: Orange Pi 3 LTS, SD-карта, питание, UART-кабель
       от второго лидара (TX/RX/GND), 5 В + мотор
3. [ ] Установка: Armbian/Ubuntu → venv → paho-mqtt/psutil → lidar_delta +
       agent; env агента (ROVER_NODE нового узла); enable юнит
4. [ ] Проверка: второй лидар на OP3 → MQTT → пульт (новый узел в /api/nodes)
5. [ ] Решение по мотору 2C (PWM+PID ~7 Гц / 2.5 В) — переносится на OP3 при
       переезде лидара с Tinkera

## Бюджет допокупок

| Позиция | Комментарий |
|---|---|
| 2 × BTS7960 | этап 2 |
| Buck 5 В / 5 А ×2 | этап 2 |
| Buck 3.3 В мелкий (или 2×AA временно) | этап 0 |
| USB-UART адаптер | этап 0, если Tinker не готов |
| USB-камера ×1 | этап 2, FPV |
| OAK-D Lite / RealSense D435i | этап 3, опционально |
| Выключатель 10 А, клеммники, DuPont, втулки М3 | этап 2 |
| LiDAR | не покупаем — есть два из пылесосов |

## Бэклог идей (ровер B и не только)

- Ровер B: 2WD на коллекторных моторах турбощёток, колёса TPU, Zero 2 W
- Циклонный пылесос для мастерской из турбины всасывания
- Мини-станок (гравёр/шлифовка) на втором моторе турбощётки
- Манипулятор роверу A на тех же моторах
- Автокормушка из моторчиков боковых щёток
