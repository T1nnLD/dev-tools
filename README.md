# dev-tools

Small, pragmatic utilities that make everyday development and ops easier.

Currently implemented:
- **health_checker** — periodic checks for endpoints/services (console or TUI)
- **log_analyser** — streaming grep-like log watcher with Telegram alerts
- **error_demux** — Rich TUI for duplicate-lines report across logs
- **tg_alarm** — minimal Telegram sender

---

## Quick start

```bash
git clone https://github.com/T1nnLD/dev-tools.git
cd dev-tools

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirments.txt
```
> The filename `requirments.txt` matches the repository.

---

## Tools

### 1) health_checker (`heath_checher.py`)

Periodic HTTP checks with optional live TUI (sparklines of latency). Sends a Telegram alarm if a request raises an exception.

**Config file (`-c`):**
```yaml
# hc.yaml
tg_id: 123456789                # Telegram chat ID for alarms
points:
  - url: https://api.example.com/health
    method: GET
  - url: https://api.example.com/ping
    method: POST
    data: '{"hello":"world"}'   # optional JSON string for POST body
```

**CLI (exact flags):**
```bash
python heath_checher.py -c hc.yaml                 # run in console mode
python heath_checher.py -c hc.yaml -i 5            # set interval (seconds), default: 10
python heath_checher.py -c hc.yaml -w              # TUI watch mode
```
Flags:
- `-c <PATH>` — **required**, path to YAML config
- `-i <INT>` — interval between checks, seconds (**default: 10**)
- `-w` — watch mode (TUI with response-time plots)

**Notes:**
- Methods supported in config: `GET`, `POST` (with `data`), `OPTIONS`.
- On exceptions during request, a message `"[ERR] service not responding"` is sent to `tg_id` via Telegram.
- TUI shows per-endpoint status and a sparkline with min/avg/max.

**TODO**
- full support database requests
- separate intervals for endpoints
- make a health_checker config generator for a fastapi projects

**Demo in watch state**
![python heath_checher.py -c hc.yaml -w](assets/health_checker.png)

---

### 2) log_analyser (`log_analyser.py`)

Tails a log file and sends matching lines to Telegram. Internally runs `tail -F`, filters lines by a **case-insensitive** extended regex, and for each match sends a message via `tg_alarm.py`.

**CLI (exact args & flags):**
```bash
python log_analyser.py /var/log/app.log "ERROR|Exception|CRITICAL" 123456789
python log_analyser.py ./nginx.error.log "5[0-9]{2}" 123456789 -i 2     # scan every 2s
```
Positional args:
- `file` — path to log file for analysis and notifications
- `mode` — extended regex, e.g. `"text1|text2"` (the `|` is the separator)
- `tgid` — Telegram chat ID

Optional flag:
- `-i <INT>` — scan interval in seconds (**default: 1**)

**What gets sent:**
- The full matching line, suffixed with `this stroke get from <path> log file`.

---

### 3) error_demux (`error_demux.py`)

Rich TUI that shows **top-N duplicate lines** per log file. Works in a one-shot mode or in `--watch` live-refresh mode. Exit with `Q`.

**One-shot examples:**
```bash
python error_demux.py app.log nginx.error.log -n 15      # top 15 per file
python error_demux.py app.log --ignore-case              # case-insensitive
python error_demux.py app.log --no-strip                 # keep surrounding spaces
```

**Watch mode examples:**
```bash
python error_demux.py app.log other.log --watch --refresh 0.5 --fullscreen
```

Flags and args (exact):
- `files...` — one or more paths (positional)
- `--top, -n <INT>` — top N lines per file (**default: 10**)
- `--ignore-case, -i` — case-insensitive counting
- `--no-strip` — do not trim surrounding spaces
- `--watch, -w` — live-refresh mode
- `--refresh <FLOAT>` — refresh interval seconds (**default: 1.0**)
- `--fullscreen, -f` — full-screen UI

**TODO:**
- add time viewing
- pipeline implementation

**Demo in watch state**
![python heath_checher.py -c hc.yaml -w](assets/error_demux.png)

---

### 4) tg_alarm (`tg_alarm.py`)

Send a message to a Telegram chat.

**CLI (exact):**
```bash
python tg_alarm.py <chat_id> "<message>"
# example
python tg_alarm.py 123456789 "Service X failed: timeout"
```
---
### 5) secret_scanner (`secret_scanner.py`)

Scan your repo or changed files for hard‑coded secrets. Uses provider‑specific regexes + entropy and supports a baseline to suppress known findings.

**Why:** catch keys/tokens before they land in main or in build artifacts.

**Key features:**
- Regex + entropy detection (AWS, GitHub, Slack, GCP, Stripe, private keys, generics).
- Works on folders/files, git‑tracked or only git‑diff via `--since`.
- Inline ignore per line: add `# secret-scan: ignore`.
- Baseline file to suppress known findings.
- JSON output for CI; exits with **code 1** if new findings are present.

**CLI (exact flags):**
```bash
# scan whole repo (text files only)
python secret_scanner.py

# scan only files changed since a ref/branch
python secret_scanner.py --since origin/main

# machine-readable output (for CI)
python secret_scanner.py --since origin/main --json

# update/create baseline (treat current findings as known)
python secret_scanner.py --update-baseline
```

**Options:**
- `paths...` — files or directories to scan (default: `.`)
- `--since <GIT_REF>` — only diff against `GIT_REF..HEAD`
- `--git-tracked` — scan only files tracked by git
- `--baseline <PATH>` — path to baseline file (**default: `.secret-scanner-baseline.json`**)
- `--update-baseline` — write current findings into the baseline and exit 0
- `--json` — JSON output
- `--no-entropy` — turn off entropy heuristics
- `--ignore <GLOB>` — add ignore pattern (can be repeated)



**Pre-commit (local):**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: secret-scanner
        name: secret-scanner
        entry: python3 secret_scanner.py --since HEAD
        language: system
        pass_filenames: false
```

**GitHub Actions (CI):**
```yaml
# .github/workflows/secret-scan.yml
name: secret-scan
on: [pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 secret_scanner.py --since origin/${{ github.base_ref }} --json
```

**Exit codes:**
- `0` — no new findings (or `--update-baseline` was used)
- `1` — new potential secrets detected


---

## Wiring the tools

- `health_checker` sends an alarm to `tg_id` on request exceptions.
- `log_analyser` filters and forwards matching lines to Telegram.
- `error_demux` is a local TUI to spot noisy duplicates across logs.

Minimal live setup with Telegram alerts only on matches:
```bash
python log_analyser.py /var/log/app.log "ERROR|Exception" 123456789 -i 1
```


---

## TODO:

- standardize the operation of all modules
- arrange all modules into a library and post them on pypi

---

# dev-tools (RU)

Небольшой набор утилит для повседневной разработки и эксплуатации.

Реализовано:
- **health_checker** — периодические проверки эндпоинтов (консоль или TUI)
- **log_analyser** — «греп» по логам с отправкой в Telegram
- **error_demux** — Rich TUI с топом дубликатов строк по файлам
- **tg_alarm** — минимальная отправка сообщений в Telegram

---

## Быстрый старт

```bash
git clone https://github.com/T1nnLD/dev-tools.git
cd dev-tools

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirments.txt
```

---

## Инструменты






### 1) health_checker (`heath_checher.py`)

Периодически проверяет URL’ы, в случае исключения шлёт алерт в Telegram. Есть TUI с «спарклайнами» задержек.

**Конфиг (`-c`):**
```yaml
tg_id: 123456789
points:
  - url: https://api.example.com/health
    method: GET
  - url: https://api.example.com/ping
    method: POST
    data: '{"hello":"world"}'
```

**Запуск (точные флаги):**
```bash
python heath_checher.py -c hc.yaml
python heath_checher.py -c hc.yaml -i 5
python heath_checher.py -c hc.yaml -w
```
Флаги:
- `-c <PATH>` — **обязателен**, путь к YAML-конфигу
- `-i <INT>` — интервал проверок в секундах (**по умолчанию: 10**)
- `-w` — режим наблюдения (TUI)

**TODO**
- полная совместимость с запросами к базам данных
- раздельные интервалы для эндпоинтов
- сделать генератор конфига  health_checker для проектов на fastapi

**Демо в состоянии просмотра**

![python heath_checher.py -c hc.yaml -w](assets/health_checker.png)

---

### 2) log_analyser (`log_analyser.py`)

Следит за лог-файлом, выбирает строки по **регэкспу** (без учёта регистра) и отправляет найденные строки в Telegram.

**Запуск (точные аргументы):**
```bash
python log_analyser.py /var/log/app.log "ERROR|Exception|CRITICAL" 123456789
python log_analyser.py ./nginx.error.log "5[0-9]{2}" 123456789 -i 2
```
Позиционные аргументы:
- `file` — путь к логу
- `mode` — расширенный регэксп (через `|` для OR)
- `tgid` — Telegram chat ID

Необязательный флаг:
- `-i <INT>` — интервал сканирования, сек (**по умолчанию: 1**)

**Отправляется:** исходная строка с припиской `this stroke get from <path> log file`.

---

### 3) error_demux (`error_demux.py`)

Показывает топ повторяющихся строк по каждому файлу. Есть разовый отчёт и `--watch` с автообновлением. Выход — клавиша `Q`.

**Разовый отчёт:**
```bash
python error_demux.py app.log nginx.error.log -n 15
python error_demux.py app.log --ignore-case
python error_demux.py app.log --no-strip
```

**Наблюдение:**
```bash
python error_demux.py app.log other.log --watch --refresh 0.5 --fullscreen
```

Флаги и аргументы (точно):
- `files...` — один или несколько файлов (позиционные)
- `--top, -n <INT>` — топ N строк для каждого файла (**по умолчанию: 10**)
- `--ignore-case, -i` — без учёта регистра
- `--no-strip` — не обрезать пробелы по краям
- `--watch, -w` — режим наблюдения
- `--refresh <FLOAT>` — интервал обновления в секундах (**по умолчанию: 1.0**)
- `--fullscreen, -f` — полноэкранный режим

**TODO:**
- показ времени
- реализация конвеера

**Demo in watch state**
![python heath_checher.py -c hc.yaml -w](assets/error_demux.png)

---

### 4) tg_alarm (`tg_alarm.py`)

Отправляет сообщение в указанный чат.

**Запуск (точно):**
```bash
python tg_alarm.py <chat_id> "<message>"
# пример
python tg_alarm.py 123456789 "Проблема с сервисом X: timeout"
```
---
### 5) secret_scanner (`secret_scanner.py`)

Сканирует репозиторий или изменённые файлы на «захардкоженные» секреты. Использует набор регэкспов по провайдерам + энтропию и поддерживает baseline для подавления известных находок.

**Зачем:** поймать ключи/токены до попадания в `main` или артефакты сборки.

**Возможности:**
- Регэкспы + энтропия (AWS, GitHub, Slack, GCP, Stripe, приватные ключи, общие шаблоны).
- Работа по папкам/файлам, только по git‑tracked или только по `git diff` через `--since`.
- Точечный игнор строки: комментарий `# secret-scan: ignore`.
- Baseline‑файл для подавления «известных» находок.
- JSON для CI; завершение **кодом 1**, если есть новые находки.

**Запуск (точные флаги):**
```bash
# скан всего репо (только текстовые файлы)
python secret_scanner.py

# скан только изменённых файлов с ветки/тэга
python secret_scanner.py --since origin/main

# JSON для CI
python secret_scanner.py --since origin/main --json

# обновить/создать baseline
python secret_scanner.py --update-baseline
```

**Опции:**
- `paths...` — файлы или директории для сканирования (по умолчанию: `.`)
- `--since <GIT_REF>` — только изменения относительно `GIT_REF..HEAD`
- `--git-tracked` — сканировать только файлы, отслеживаемые git
- `--baseline <PATH>` — путь к baseline (**по умолчанию: `.secret-scanner-baseline.json`**)
- `--update-baseline` — записать текущие находки в baseline и выйти с кодом 0
- `--json` — вывести JSON
- `--no-entropy` — отключить энтропийные эвристики
- `--ignore <GLOB>` — добавить шаблон игнора (флаг можно повторять)

**pre-commit (локально):**
```yaml
repos:
  - repo: local
    hooks:
      - id: secret-scanner
        name: secret-scanner
        entry: python3 secret_scanner.py --since HEAD
        language: system
        pass_filenames: false
```

**GitHub Actions (CI):**
```yaml
name: secret-scan
on: [pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 secret_scanner.py --since origin/${{ github.base_ref }} --json
```

**Коды выхода:**
- `0` — нет новых находок (или был использован `--update-baseline`)
- `1` — обнаружены новые потенциальные секреты



---

## Как связать

- `health_checker` — шлёт оповещение при исключении запроса.
- `log_analyser` — отправляет найденные по регэкспу строки.
- `error_demux` — локальный просмотрщик/агрегатор (без Telegram).

Минимальный живой сценарий с алертами только на совпадения:
```bash
python log_analyser.py /var/log/app.log "ERROR|Exception" 123456789 -i 1
```

---

## TODO:

- стандартизировать работу всех модулей
- оформить все модули в библиотеку и выложить на pypi





