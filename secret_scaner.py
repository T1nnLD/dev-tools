#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
secret_scanner.py — простой оффлайн-сканер секретов:
- детект по regex + энтропии
- baseline для подавления известных находок
- работу по git diff (--since)
- JSON/читаемый вывод
"""

from __future__ import annotations
import argparse
import base64
import fnmatch
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


# ---------------------- настройки ----------------------

DEFAULT_IGNORE_GLOBS = {
    ".git/**",
    "**/.git/**",
    "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.pdf",
    "**/*.ico", "**/*.zip", "**/*.gz", "**/*.tgz", "**/*.bz2", "**/*.xz",
    "**/*.7z", "**/*.mp4", "**/*.mp3", "**/*.mov", "**/*.avi",
    "**/.venv/**", "**/venv/**", "**/__pycache__/**",
    "**/node_modules/**",
    "**/*.min.js",
}

# простые эвристики: ключевики по соседству повышают уверенность
CONTEXT_KEYWORDS = [
    "secret", "token", "apikey", "api_key", "passwd", "password", "pwd",
    "private_key", "access_key", "refresh_token", "auth", "bearer", "credential",
]

# главные регулярки (минимально необходимые, можно расширять)
REGEXPS: Dict[str, re.Pattern] = {
    # AWS
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_access_key": re.compile(r"(?i)aws(.{0,20})?(secret|sk|secret_access_key)['\"=: ]{1,5}([0-9a-zA-Z/+]{40})"),
    # GitHub
    "github_token": re.compile(r"gh[pousr]_[0-9a-zA-Z]{36,251}"),
    # Slack
    "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,48}"),
    # Google
    "gcp_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    # Stripe
    "stripe_live": re.compile(r"sk_live_[0-9a-zA-Z]{24,}"),
    "stripe_test": re.compile(r"sk_test_[0-9a-zA-Z]{24,}"),
    # Private key headers
    "private_key": re.compile(r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
    # Generic assignments like PASSWORD=..., token: "...", etc.
    "generic_password_assign": re.compile(r"(?i)\b(pass(word)?|pwd)\b\s*[:=]\s*['\"][^'\"\s]{6,}['\"]"),
    "generic_token_assign": re.compile(r"(?i)\b(token|secret|apikey|api_key|bearer)\b\s*[:=]\s*['\"][0-9A-Za-z_\-\.=]{16,}['\"]"),
    # Base64-точно «секретные» куски (с контекстом определим)
    "base64_credentialish": re.compile(r"\b(?:[A-Za-z0-9+/]{24,}={0,2})\b"),
}

# длина строки, с которой начинаем считать энтропию
ENTROPY_MIN_LEN = 20
ENTROPY_THRESHOLD = 4.0  # бита/символ — прагматичный порог для подозрительных строк


# ---------------------- модели ----------------------

@dataclass
class Finding:
    file: str
    line: int
    col: int
    rule: str
    match: str
    context: str
    score: float  # 0..1 уверенность
    fingerprint: str  # для baseline

    def masked(self) -> "Finding":
        # частично маскируем, чтобы не утекало дальше
        m = self.match
        if len(m) > 8:
            m = m[:4] + "…" + m[-4:]
        else:
            m = "…" * min(4, len(m))
        return Finding(
            file=self.file, line=self.line, col=self.col, rule=self.rule,
            match=m, context=self.context, score=self.score, fingerprint=self.fingerprint
        )


# ---------------------- утилиты ----------------------

def is_binary(content: bytes) -> bool:
    if b"\x00" in content[:4096]:
        return True
    # эвристика: высокий процент non-text
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(32, 127)))
    nontext = content.translate(None, text_chars)
    return len(nontext) / max(1, len(content)) > 0.30


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for ch in s:
        freq[ch] = freq.get(ch, 0) + 1
    ent = 0.0
    n = len(s)
    for c in freq.values():
        p = c / n
        ent -= p * math.log2(p)
    return ent


def line_fingerprint(path: str, line_no: int, rule: str, match_text: str) -> str:
    # стабильный отпечаток для baseline (без привязки к колонке)
    h = hashlib.sha256()
    h.update(path.encode("utf-8", "ignore"))
    h.update(str(line_no).encode())
    h.update(rule.encode())
    # не храним полный секрет — только хэш
    h.update(hashlib.sha256(match_text.encode("utf-8", "ignore")).digest())
    return h.hexdigest()


def mask_newlines(s: str) -> str:
    return s.replace("\n", "\\n")


def read_text_safely(p: Path) -> Optional[str]:
    try:
        b = p.read_bytes()
    except Exception:
        return None
    if is_binary(b) or len(b) > 1_000_000:  # 1MB лимит
        return None
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return b.decode("latin1")
        except Exception:
            return None


def matches_globs(path: Path, globs: Set[str]) -> bool:
    sp = str(path.as_posix())
    for pattern in globs:
        if fnmatch.fnmatch(sp, pattern):
            return True
    return False


def git_tracked_files(root: Path) -> List[Path]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=str(root))
        return [root / Path(x) for x in out.decode().splitlines() if x.strip()]
    except Exception:
        return []


def git_changed_files(root: Path, since: str) -> List[Path]:
    try:
        out = subprocess.check_output(["git", "diff", "--name-only", since, "HEAD"], cwd=str(root))
        return [root / Path(x) for x in out.decode().splitlines() if x.strip()]
    except Exception:
        return []


# ---------------------- детектор ----------------------

def detect_in_text(path: Path, text: str) -> Iterable[Finding]:
    findings: List[Finding] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        if "secret-scan: ignore" in line:
            continue

        # контекстный бонус, если около матча есть ключевое слово
        context_bonus = 0.0
        lower = line.lower()
        if any(k in lower for k in CONTEXT_KEYWORDS):
            context_bonus = 0.15

        for rule_name, pattern in REGEXPS.items():
            for m in pattern.finditer(line):
                token = m.group(0)
                # отсекаем очевидные фэйки
                if token.lower().startswith(("password", "passwd")) and "example" in lower:
                    continue

                # энтропия для generic/base64 случаев
                ent = 0.0
                if rule_name in ("base64_credentialish", "generic_token_assign", "generic_password_assign"):
                    candidate = token
                    ent = shannon_entropy(candidate) if len(candidate) >= ENTROPY_MIN_LEN else 0.0

                # общий «скор»
                score = 0.6 + context_bonus
                if ent >= ENTROPY_THRESHOLD:
                    score += 0.2
                if rule_name in ("generic_token_assign", "generic_password_assign", "base64_credentialish"):
                    score = min(score, 0.85)

                fp = line_fingerprint(str(path), i, rule_name, token)
                findings.append(Finding(
                    file=str(path),
                    line=i,
                    col=m.start() + 1,
                    rule=rule_name,
                    match=token,
                    context=line.strip()[:240],
                    score=round(min(score, 0.99), 2),
                    fingerprint=fp
                ))

        # энтропия «как есть» для длинных токеноподобных слов (без regex’ов)
        for word in re.findall(r"[A-Za-z0-9_\-\.=]{20,}", line):
            if any(word.startswith(prefix) for prefix in ("http", "https", "AKIA")):
                continue
            ent = shannon_entropy(word)
            if ent >= ENTROPY_THRESHOLD + 0.5:
                fp = line_fingerprint(str(path), i, "high_entropy", word)
                findings.append(Finding(
                    file=str(path), line=i, col=line.find(word)+1, rule="high_entropy",
                    match=word, context=line.strip()[:240],
                    score=0.7 + context_bonus, fingerprint=fp
                ))
    return findings


def load_baseline(path: Optional[Path]) -> Set[str]:
    if not path or not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("fingerprints", []))
    except Exception:
        return set()


def save_baseline(path: Path, fingerprints: Set[str]) -> None:
    payload = {
        "version": 1,
        "fingerprints": sorted(fingerprints),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------- сканер ----------------------

def scan_paths(paths: List[Path], root: Path, ignore_globs: Set[str]) -> List[Finding]:
    findings: List[Finding] = []
    for p in paths:
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_dir():
                    continue
                if matches_globs(root.relative_to(root) / sub, ignore_globs):
                    continue
                text = read_text_safely(sub)
                if text is None:
                    continue
                findings.extend(detect_in_text(sub, text))
        else:
            if not p.exists():
                continue
            if matches_globs(root.relative_to(root) / p, ignore_globs):
                continue
            text = read_text_safely(p)
            if text is None:
                continue
            findings.extend(detect_in_text(p, text))
    return findings


def decide_target_files(args, root: Path, ignore_globs: Set[str]) -> List[Path]:
    if args.since:
        files = git_changed_files(root, args.since)
    elif args.git_tracked:
        files = git_tracked_files(root)
    else:
        # если ничего не указано — текущая директория
        files = [root]
    # фильтруем игноры
    result: List[Path] = []
    for p in files:
        if p.is_dir():
            result.append(p)
        else:
            if not matches_globs(root.relative_to(root) / p, ignore_globs):
                result.append(p)
    return result


# ---------------------- CLI ----------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Scan repo/files for hardcoded secrets.")
    ap.add_argument("paths", nargs="*", default=["."], help="Files or directories to scan (default: current dir)")
    ap.add_argument("--since", help="Scan only files changed since GIT_REF, e.g. --since origin/main")
    ap.add_argument("--git-tracked", action="store_true", help="Scan only git tracked files")
    ap.add_argument("--baseline", default=".secret-scanner-baseline.json", help="Baseline file path")
    ap.add_argument("--update-baseline", action="store_true", help="Write current findings to baseline and exit 0")
    ap.add_argument("--json", action="store_true", help="Output JSON")
    ap.add_argument("--no-entropy", action="store_true", help="Disable entropy heuristics")
    ap.add_argument("--ignore", action="append", help="Add glob pattern to ignore (can be repeated)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(".").resolve()

    ignore_globs = set(DEFAULT_IGNORE_GLOBS)
    if args.ignore:
        ignore_globs |= set(args.ignore)

    # разрешаем отключить энтропию при желании
    global ENTROPY_THRESHOLD
    if args.no_entropy:
        ENTROPY_THRESHOLD = 9999

    targets = decide_target_files(args, root, ignore_globs)
    findings = scan_paths(targets, root, ignore_globs)

    # применяем baseline
    baseline_fp = load_baseline(Path(args.baseline) if args.baseline else None)
    new_findings = [f for f in findings if f.fingerprint not in baseline_fp]

    if args.update_baseline:
        all_fp = baseline_fp | {f.fingerprint for f in findings}
        save_baseline(Path(args.baseline), all_fp)
        print(f"Baseline updated with {len(findings)} findings → {args.baseline}")
        return 0

    # вывод
    if args.json:
        payload = {
            "findings": [asdict(f.masked()) for f in new_findings],
            "count": len(new_findings),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not new_findings:
            print("✅ No new secrets found.")
        else:
            print(f"❗ Potential secrets: {len(new_findings)} (masked below)\n")
            for f in new_findings:
                fm = f.masked()
                print(f"{fm.file}:{fm.line}:{fm.col}  [{fm.rule}] score={fm.score}")
                print(f"  match: {fm.match}")
                print(f"  ctx  : {mask_newlines(fm.context)}")
                print(f"  fp   : {fm.fingerprint[:12]}…")
                print()

    return 1 if new_findings else 0


if __name__ == "__main__":
    sys.exit(main())

