# dev-tools

Небольшой, но полезный набор утилит для повседневной работы разработчика.

[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://www.python.org/)


## Что внутри

| Команда              | Краткое описание                                                                 | Основной режим       |
|----------------------|----------------------------------------------------------------------------------|----------------------|
| `health-checker`     | Периодическая проверка HTTP-эндпоинтов + алерты в Telegram + TUI со спарклайнами | демон / TUI          |
| `secret-scanner`     | Поиск захардкоженных секретов (pre-push hook, CI, ручной запуск)                 | CLI + git hook + CI  |
| `log-analyser`       | Следит за лог-файлом и отправляет совпадения по regexp в Telegram                | tail + grep + TG     |
| `error-demux`        | Топ повторяющихся строк/ошибок в логах (разовый отчёт или watch-режим)          | анализ логов         |
| `tg-alarm`           | Быстрая отправка сообщения в Telegram из терминала или кода                     | одноразовая отправка |
| `git-sync`           | Автоматическая синхронизация репозитория + выполнение команд деплоя             | демон                |
| `timers`             | Таймеры и декораторы для замера времени выполнения функций (sync/async)         | библиотека           |
| `logger`             | Удобный Rich-логгер с кастомным форматом и цветами                              | библиотека           |

Rich-вывод используется почти везде, где есть человекочитаемый интерфейс.

## Установка

```bash
# Самый простой способ
pip install git+https://github.com/T1nnLD/dev-tools.git

# Рекомендуемый способ в 2025–2026 (быстрее, чище, меньше мусора)
uv pip install git+https://github.com/T1nnLD/dev-tools.git
```

После установки команды будут доступны сразу в терминале.

## Быстрый старт — самые популярные сценарии

```bash
# Защита от утечки секретов перед push
secret-scanner --since origin/main

# Мониторинг здоровья сервисов с красивым TUI
health-checker -c health.yaml -w

# Следить за ошибками в логе → алерты в Telegram
log-analyser /var/log/app.log "ERROR|Exception|CRITICAL" 123456789 -i 2

# Топ частых ошибок в логах (с автообновлением)
error-demux app.log nginx.error.log -n 10 --watch
```

## Подробное описание инструментов

### 1. health-checker

Проверяет HTTP-эндпоинты с заданным интервалом. При ошибке — алерт в Telegram.  
Есть режим TUI с графиками задержек (sparklines).

```bash
health-checker -c config.yaml
health-checker -c config.yaml -i 5 -w
```

**Флаги:**
- `-c, --config PATH`     (обязательно) путь к yaml
- `-i, --interval SEC`    интервал проверок (по умолчанию: 10)
- `-w, --watch`           запустить TUI

Пример `config.yaml`:
```yaml
tg_id: 987654321
points:
  - url: https://api.example.com/health
    method: GET
    timeout: 5
  - url: https://example.com/ping
    method: POST
    json: {"status": "check"}
    timeout: 3
```

**Планируется:**
- проверки tcp/port
- проверки баз данных
- генератор конфига для FastAPI

### 2. secret-scanner

Сканер секретов (AWS, GCP, GitHub token, приватные ключи, высокая энтропия и др.).

```bash
secret-scanner
secret-scanner --since origin/main
secret-scanner --update-baseline
secret-scanner --json > report.json
```

**Основные флаги:**
- `--since <ref>`          только изменения относительно ветки/коммита
- `--git-tracked`          только отслеживаемые git файлы
- `--baseline PATH`        файл исключений (.secret-scanner-baseline.json по умолчанию)
- `--update-baseline`      обновить baseline и выйти с кодом 0
- `--no-entropy`           отключить энтропийную проверку
- `--json`                 вывод в JSON (для CI)

**Пример pre-push хука** (.git/hooks/pre-push):
```bash
#!/usr/bin/env bash
current_branch=$(git rev-parse --abbrev-ref HEAD)

secret-scaner.py --since origin/$current_branch
```

### 3. log-analyser

Следит за лог-файлом и отправляет совпадения по регулярке в Telegram.

```bash
log-analyser /var/log/nginx/error.log "5[0-9]{2}" 123456789 -i 3
log-analyser app.log "(ERROR|CRITICAL|Exception)" 987654321
```

Аргументы (позиционные):
1. путь к файлу
2. регулярное выражение (без учёта регистра)
3. Telegram chat ID

Флаги:
- `-i, --interval SEC`     интервал проверки (по умолчанию 1)

### 4. error-demux

Топ повторяющихся строк в логах. Поддерживает watch-режим.

```bash
error-demux app.log nginx.error.log -n 15 --watch --refresh 2
error-demux error.log --ignore-case
```

Флаги:
- `-n, --top N`            размер топа (по умолчанию 10)
- `--watch, -w`            режим наблюдения
- `--refresh SEC`          частота обновления (по умолчанию 1.0)
- `--ignore-case, -i`
- `--no-strip`             не убирать пробелы по краям

Выход из watch — клавиша `q`.

### 5. tg-alarm

Отправка сообщения в Telegram.

```bash
tg-alarm 123456789 "Деплой завершён успешно"
tg-alarm 987654321 "Сервис упал" --silent
```

### 6. git-sync

Автосинхронизация репозитория + выполнение команд после синхронизации.

```bash
git-sync -c git-sync.yaml
git-sync --generate-config
```

Пример конфига `git-sync.yaml`:
```yaml
branch: main
interval: 30
ignore:
  - secrets/**
  - .env
deploy:
  - sudo systemctl restart myapp
  - echo "Deploy done"
```

### 7. timers (библиотека)

```python
from dev_tools.timers import timer_ms, InterTimer

@timer_ms("important_calc")
def heavy():
    ...

@timer_ms(fmt='{time} >>> [bold {color}]{label}[/]')
async def some_func():
    ...

timer = InterTimer()
timer.start()
# код
timer.stop("stage1")
```

### 8. logger (библиотека)

```python
from dev_tools.logger import log, set_log_format

log("Успех!", "green")
set_log_format("[bold cyan]{time}[/] {text}")
```

## TODO (ближайшие планы)

- Единый интерфейс: `devtool <command> ...`
- Автогенерация конфигов для health-checker
- Интеграция с FastAPI (middleware + error handling)
- Blue-green deploy в git-sync


---
