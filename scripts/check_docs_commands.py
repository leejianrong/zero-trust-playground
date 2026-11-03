#!/usr/bin/env python3
"""Fail if the docs or README mention a `make` target the Makefile does not define,
or if the nav in zensical.toml points at a page that does not exist."""
import pathlib
import re
import sys
import tomllib

root = pathlib.Path(__file__).resolve().parent.parent
targets = set(re.findall(r"^([a-z0-9-]+):", (root / "Makefile").read_text(), re.M))
pages = [*root.glob("docs/tutorial/**/*.md"), root / "README.md"]
problems = []

for page in pages:
    for target in re.findall(r"\bmake ([a-z][a-z0-9-]*)", page.read_text()):
        if target not in targets:
            problems.append(f"{page.relative_to(root)}: `make {target}` is not a Makefile target")


def nav_files(items):
    for item in items:
        for value in item.values():
            if isinstance(value, str):
                yield value
            else:
                yield from nav_files(value)


nav = tomllib.loads((root / "zensical.toml").read_text())["project"]["nav"]
for rel in nav_files(nav):
    if not (root / "docs/tutorial" / rel).exists():
        problems.append(f"zensical.toml nav: {rel} does not exist")

print("\n".join(problems) or f"ok: {len(pages)} pages, {len(targets)} make targets")
sys.exit(1 if problems else 0)
