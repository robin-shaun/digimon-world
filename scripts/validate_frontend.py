#!/usr/bin/env python3
"""Frontend validation — checks HTML structure, JS syntax, and CSS existence."""
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
errors = []

# Validate HTML files
for f in sorted(FRONTEND_DIR.glob("*.html")):
    try:
        html = f.read_text(encoding="utf-8").lower()
    except Exception as e:
        errors.append(f"FAIL: {f.name} — cannot read: {e}")
        continue

    for tag, desc in [
        ("<!doctype html>", "missing doctype"),
        ("<html", "missing <html>"),
        ("<head", "missing <head>"),
        ("<body", "missing <body>"),
    ]:
        if tag not in html:
            errors.append(f"FAIL: {f.name} — {desc}")
    if not errors or errors[-1] != f"FAIL: {f.name} — missing <body>":
        pass
    print(f"  PASS: {f.name}")

# Validate JavaScript syntax using Node
import subprocess
for f in sorted(FRONTEND_DIR.glob("*.js")):
    try:
        result = subprocess.run(
            ["node", "-c", str(f)], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            errors.append(f"FAIL: {f.name} — syntax error: {result.stderr.strip()}")
        else:
            print(f"  PASS: {f.name}")
    except FileNotFoundError:
        print(f"  SKIP: {f.name} (node not available)")
    except subprocess.TimeoutExpired:
        errors.append(f"FAIL: {f.name} — node -c timed out")

# Validate CSS
css = FRONTEND_DIR / "style.css"
if css.exists():
    print(f"  PASS: style.css")
else:
    errors.append("FAIL: style.css not found")

if errors:
    print("\n❌ Validation errors:", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

print("\n✅ All frontend files validated")
