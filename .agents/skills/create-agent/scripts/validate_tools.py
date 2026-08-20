#!/usr/bin/env python3
"""
Validate IBM i MCP tool YAML files against the live ibmi-mcp-server schema.

Downloads the authoritative JSON Schema from the ibmi-mcp-server repository,
validates the given tool YAML file(s) against it entirely in memory, and
discards the schema afterwards — nothing is written to disk, so this repo can
never carry a stale copy of the schema.

Usage:
    uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/my-toolset.yaml
    uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/   # every *.yaml in the dir
    uv run python .agents/skills/create-agent/scripts/validate_tools.py --schema-url <url> tools/my-toolset.yaml

Exit codes:
    0   every file passed schema validation
    1   at least one file failed validation (schema violations or unparseable YAML)
    2   environment or usage error (schema download failed, missing dependency,
        unreadable path, no YAML files found)
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import NoReturn

DEFAULT_SCHEMA_URL = (
    "https://raw.githubusercontent.com/IBM/ibmi-mcp-server"
    "/refs/heads/main/packages/server/src/ibmi-mcp-server/schemas/json/sql-tools-config.json"
)

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ENV = 2


def fail_env(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(EXIT_ENV)


def download_schema(url: str, timeout: float) -> dict:
    """Fetch the JSON Schema into memory. Never touches disk."""
    print(f"Downloading schema: {url}", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as e:
        fail_env(
            f"schema download failed: HTTP {e.code} {e.reason} for {url}\n"
            "       The schema may have moved in the ibmi-mcp-server repo — check the URL, "
            "or pass a corrected one with --schema-url."
        )
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        fail_env(
            f"schema download failed: {reason}\n"
            "       Check your network connection and retry. The schema is fetched fresh on "
            "every run (it is deliberately not stored in this repo)."
        )

    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as e:
        fail_env(f"schema download returned invalid JSON ({e}) — the URL may not point at the raw schema file: {url}")

    if not isinstance(schema, dict):
        fail_env(f"schema download returned {type(schema).__name__}, expected a JSON Schema object: {url}")
    print("Schema downloaded (held in memory only — discarded on exit).")
    return schema


def collect_yaml_files(paths: list[Path]) -> list[Path]:
    """Expand the given files/directories into a sorted list of YAML files."""
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            found = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
            if not found:
                fail_env(f"no YAML files found in directory: {path}")
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            fail_env(f"no such file or directory: {path}")
    return files


def validate_file(path: Path, validator) -> list[str]:  # type: ignore[no-untyped-def]
    """Validate one YAML file. Returns human-readable error strings (empty if valid)."""
    import yaml

    try:
        data = yaml.safe_load(path.read_text())
    except OSError as e:
        fail_env(f"cannot read {path}: {e}")
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return [f"expected a YAML mapping at the root, got {type(data).__name__}"]

    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"at {where}: {error.message}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate tool YAML files against the ibmi-mcp-server sql-tools-config schema "
        "(downloaded fresh, never stored in this repo)."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        metavar="PATH",
        help="Tool YAML file(s) to validate, or directories to scan for *.yaml / *.yml",
    )
    parser.add_argument(
        "--schema-url",
        default=DEFAULT_SCHEMA_URL,
        help="Override the schema URL (default: the ibmi-mcp-server repo's main branch)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Schema download timeout in seconds (default: 30)",
    )
    args = parser.parse_args()

    try:
        import yaml  # noqa: F401
        from jsonschema import validators
    except ImportError as e:
        fail_env(
            f"missing dependency: {e.name}\n"
            "       Install the project environment first: ./scripts/venv_setup.sh "
            "(or run via `uv run python ...` from the repo root)."
        )

    files = collect_yaml_files(args.paths)
    schema = download_schema(args.schema_url, args.timeout)

    validator_cls = validators.validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except Exception as e:  # jsonschema.SchemaError
        fail_env(f"downloaded schema is not itself a valid JSON Schema: {e}")
    validator = validator_cls(schema)

    print()
    failed = 0
    for path in files:
        errors = validate_file(path, validator)
        if errors:
            failed += 1
            print(f"✗ {path} — {len(errors)} error(s)")
            for err in errors:
                print(f"    {err}")
        else:
            print(f"✓ {path}")

    print()
    if failed:
        print(f"{failed} of {len(files)} file(s) FAILED schema validation.")
        print("Fix the YAML and re-run. Common mistakes and the validation-error → fix map:")
        print(".agents/skills/create-agent/references/tool-design-reference.md §9–§10")
        return EXIT_INVALID

    print(f"All {len(files)} file(s) passed schema validation.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
