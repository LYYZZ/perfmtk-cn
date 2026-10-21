#!/usr/bin/env python3
"""Apply the Simplified-Chinese localization to a PerfMTK-Manager source tree.

Why a script instead of a git patch/merge:
    Upstream adds new UI strings to lib/localization/app_locales.dart on almost every
    release. A stored diff would conflict every single time. Instead this script
    *regenerates* the `zh` map from tools/zh_strings.json every run, falling back to
    the English text for any key we have not translated yet. Nothing here depends on
    line numbers, so upstream refactors of the locale file do not break it.

Design notes:
    * Idempotent: an existing `zh` map is removed and regenerated.
    * Only 3 small registration points are touched (app.dart, the language picker and
      the settings screen). Each is guarded, so re-running is safe.
    * New upstream keys are reported, so translations can be filled in over time.

Usage:
    python tools/apply_zh.py <repo-root>
    python tools/apply_zh.py <repo-root> --extract        # rebuild zh_strings.json
    python tools/apply_zh.py <repo-root> --check-only     # report, change nothing
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOCALE_FILE = Path("lib/localization/app_locales.dart")
APP_FILE = Path("lib/app.dart")
PICKER_FILE = Path("lib/presentation/widgets/language_selection_sheet.dart")
SETTINGS_FILE = Path("lib/presentation/screens/settings_screen.dart")
STRINGS_FILE = Path("tools/zh_strings.json")

EN_START = re.compile(r"static const Map<String,\s*dynamic>\s+en\s*=\s*\{")
ZH_START = re.compile(r"static const Map<String,\s*dynamic>\s+zh\s*=\s*\{")
MAP_ENTRY = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)\s*,\s*$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def parse_dart_string(raw: str) -> str:
    """Parse a single-quoted or double-quoted Dart string literal."""
    raw = raw.strip()
    if not raw or raw[0] not in "'\"":
        return raw
    quote = raw[0]
    out: list[str] = []
    i = 1
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            i += 2
            continue
        if ch == quote:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def to_dart_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def find_map_block(lines: list[str], start_re: re.Pattern[str]) -> tuple[int, int] | None:
    """Return (first_entry_index, closing_brace_index) for a map declaration."""
    start = None
    for i, line in enumerate(lines):
        if start_re.search(line):
            start = i
            break
    if start is None:
        return None
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == "};":
            return start + 1, j
    return None


def collect_entries(lines: list[str], start: int, end: int) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in lines[start:end]:
        m = MAP_ENTRY.match(line)
        if m:
            entries[m.group(1)] = parse_dart_string(m.group(2))
    return entries


def strip_existing_zh(text: str) -> str:
    """Remove a previously generated zh map so we can regenerate it cleanly."""
    lines = text.split("\n")
    block = find_map_block(lines, ZH_START)
    if block is None:
        return text
    start, closing = block
    # drop the declaration line (start-1) through the closing brace
    del lines[start - 1 : closing + 1]
    # collapse a trailing blank line left behind
    if start - 1 < len(lines) and lines[start - 1].strip() == "" and start - 2 >= 0 and lines[start - 2].strip() == "":
        del lines[start - 1]
    return "\n".join(lines)


def registration_patches(repo: Path) -> list[str]:
    """Apply the three small registration edits. Returns a list of messages."""
    messages: list[str] = []

    # 1) lib/app.dart - register the locale and default to it for zh systems
    app = repo / APP_FILE
    text = read(app)
    if "MapLocale('zh'" not in text:
        anchor = re.search(r"( *)(const MapLocale\('es',\s*AppLocale\.es\),\n)", text)
        if not anchor:
            raise SystemExit(f"[FAIL] {APP_FILE}: cannot find the es MapLocale anchor")
        indent = anchor.group(1)
        text = text[: anchor.end()] + f"{indent}const MapLocale('zh', AppLocale.zh),\n" + text[anchor.end():]
        messages.append(f"{APP_FILE}: registered MapLocale('zh')")
    else:
        messages.append(f"{APP_FILE}: MapLocale('zh') already present")

    if "systemLanguage == 'zh'" not in text:
        old = re.search(r"initLanguageCode:\s*systemLanguage == 'es' \? 'es' : 'en',", text)
        if old:
            text = text.replace(
                old.group(0),
                "initLanguageCode: systemLanguage == 'es'\n"
                "          ? 'es'\n"
                "          : (systemLanguage == 'zh' ? 'zh' : 'en'),",
            )
            messages.append(f"{APP_FILE}: default to zh for Chinese systems")
        else:
            messages.append(f"[warn] {APP_FILE}: initLanguageCode anchor not found, skipped")
    write(app, text)

    # 2) language picker sheet
    picker = repo / PICKER_FILE
    text = read(picker)
    if "code: 'zh'" not in text:
        anchor = re.search(r"( *)(\(code: 'es'[^\n]*\),\n)", text)
        if not anchor:
            raise SystemExit(f"[FAIL] {PICKER_FILE}: cannot find the es entry anchor")
        indent = anchor.group(1)
        text = (
            text[: anchor.end()]
            + f"{indent}(code: 'zh', icon: '\U0001F1E8\U0001F1F3', title: '\u7b80\u4f53\u4e2d\u6587', subtitle: 'Chinese'),\n"
            + text[anchor.end():]
        )
        messages.append(f"{PICKER_FILE}: added the Chinese entry")
    else:
        messages.append(f"{PICKER_FILE}: Chinese entry already present")
    write(picker, text)

    # 3) settings screen - display name for the current language
    settings = repo / SETTINGS_FILE
    text = read(settings)
    if "case 'zh':" not in text:
        anchor = re.search(r"( *)case 'en':", text)
        if not anchor:
            messages.append(f"[warn] {SETTINGS_FILE}: case 'en' anchor not found, skipped")
        else:
            indent = anchor.group(1)
            text = (
                text[: anchor.start()]
                + f"{indent}case 'zh':\n{indent}  return '\u7b80\u4f53\u4e2d\u6587';\n"
                + text[anchor.start():]
            )
            messages.append(f"{SETTINGS_FILE}: added the Chinese display name")
    else:
        messages.append(f"{SETTINGS_FILE}: Chinese display name already present")
    write(settings, text)

    return messages


def drop_unsupported_api(repo: Path) -> str | None:
    """ScrollCacheExtent exists only in newer Flutter SDKs. Dropping the argument is
    safe: it is a scroll pre-render hint, not behaviour."""
    target = repo / "lib/presentation/screens/app_profiles_screen.dart"
    if not target.exists():
        return None
    text = read(target)
    if "scrollCacheExtent" not in text:
        return None
    new_text = "\n".join(line for line in text.split("\n") if "scrollCacheExtent" not in line)
    write(target, new_text)
    return f"{target.relative_to(repo)}: removed scrollCacheExtent (needs a newer Flutter SDK)"


def normalize_gradle_properties(repo: Path) -> str | None:
    """Upstream ships android/gradle.properties pinned to the author's own JDK:
        org.gradle.java.home=C:\\Program Files\\Android\\openjdk\\jdk-21.0.8
    That path only exists on his Windows machine, so every build elsewhere dies with
    "Java home supplied is invalid". Drop the line and let the runner's JDK be used."""
    path = repo / "android/gradle.properties"
    if not path.exists():
        return None
    lines = read(path).split("\n")
    kept = [line for line in lines if not line.strip().startswith("org.gradle.java.home")]
    if len(kept) == len(lines):
        return None
    write(path, "\n".join(kept))
    return "android/gradle.properties: removed org.gradle.java.home (author's local JDK path)"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return 2

    repo = Path(args[0]).resolve()
    if not (repo / LOCALE_FILE).exists():
        print(f"[FAIL] {LOCALE_FILE} not found under {repo}")
        return 1

    locale_text = strip_existing_zh(read(repo / LOCALE_FILE))
    lines = locale_text.split("\n")
    block = find_map_block(lines, EN_START)
    if block is None:
        print("[FAIL] cannot locate the `en` map in app_locales.dart")
        return 1
    english = collect_entries(lines, *block)

    strings_path = repo / STRINGS_FILE
    if "--extract" in flags:
        zh_block = find_map_block(read(repo / LOCALE_FILE).split("\n"), ZH_START)
        if zh_block is None:
            print("[FAIL] --extract needs an existing zh map")
            return 1
        existing = collect_entries(read(repo / LOCALE_FILE).split("\n"), *zh_block)
        strings_path.parent.mkdir(parents=True, exist_ok=True)
        strings_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"extracted {len(existing)} translated strings -> {STRINGS_FILE}")
        return 0

    translations: dict[str, str] = {}
    if strings_path.exists():
        translations = json.loads(strings_path.read_text(encoding="utf-8"))

    missing = sorted(k for k in english if k not in translations)
    stale = sorted(k for k in translations if k not in english)

    if "--check-only" in flags:
        print(f"en keys: {len(english)}  translated: {len(english) - len(missing)}")
        if missing:
            print("missing translations:", ", ".join(missing))
        if stale:
            print("stale translations:", ", ".join(stale))
        return 0

    # regenerate the zh map: translated value if we have one, English as fallback
    body = ["  // Simplified Chinese (zh) - generated by tools/apply_zh.py", "  static const Map<String, dynamic> zh = {"]
    for key in english:
        value = translations.get(key) or english[key]
        body.append(f"    {key}: {to_dart_string(value)},")
    body.append("  };")
    body.append("")

    lines = locale_text.split("\n")
    insert_at = None
    for i, line in enumerate(lines):
        if "static String getValue" in line:
            insert_at = i
            break
    if insert_at is None:
        print("[FAIL] cannot find the getValue() anchor in app_locales.dart")
        return 1
    while insert_at > 0 and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines[insert_at:insert_at] = body
    write(repo / LOCALE_FILE, "\n".join(lines))
    print(f"app_locales.dart: wrote zh map with {len(english)-len(missing)} translated / {len(english)} total keys")

    for msg in registration_patches(repo):
        print(msg)

    compat = drop_unsupported_api(repo)
    if compat:
        print(compat)

    gradle = normalize_gradle_properties(repo)
    if gradle:
        print(gradle)

    if missing:
        print(f"[note] {len(missing)} new untranslated key(s) currently show English:")
        print("       " + ", ".join(missing))
    if stale:
        print(f"[note] {len(stale)} stale key(s) in zh_strings.json (safe to drop): {', '.join(stale)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
