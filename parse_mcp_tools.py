#!/usr/bin/env python3
"""
Parse MCP tool YAML files, validate against the ibmi-mcp-server JSON schema,
and generate a consolidated JSON mapping of toolsets to their tool lists.

Reads all YAML files in the tools/ directory, validates each against
sql-tools-config.schema.json, extracts the `toolsets` section from each,
and writes a single JSON file mapping every toolset name to its list of
tool names.

Usage:
    python parse_mcp_tools.py
    python parse_mcp_tools.py --tools-dir tools --output tools/toolsets.json
    python parse_mcp_tools.py --skip-validation
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# Schema is bundled in the tools directory
DEFAULT_SCHEMA_PATH = Path("tools/sql-tools-config.schema.json")


def validate_yaml_file(data: dict, schema: dict, filename: str) -> list[str]:
    """
    Validate a parsed YAML dict against the JSON schema.

    Returns a list of human-readable error strings (empty if valid).
    """
    try:
        from jsonschema import Draft7Validator  # type: ignore[import-untyped]
    except ImportError:
        return [f"{filename}: jsonschema not installed, skipping validation"]

    validator = Draft7Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"{filename}: {path} -> {error.message}")
    return errors


def parse_yaml_tools(tools_dir: Path, schema: dict | None = None) -> tuple[dict, list[str]]:
    """
    Parse all YAML files in tools_dir and extract toolset-to-tool mappings.

    Args:
        tools_dir: Directory containing YAML tool files
        schema: Optional JSON schema dict for validation

    Returns:
        (toolsets_dict, validation_errors_list)

    toolsets_dict structure:
    {
        "toolset_name": {
            "tools": ["tool_a", "tool_b"],
            "source": "filename.yaml",
            "title": "...",          # if present
            "description": "..."     # if present
        }
    }
    """
    toolsets: dict[str, dict[str, Any]] = {}
    all_errors: list[str] = []

    yaml_files = sorted(tools_dir.glob("*.yaml")) + sorted(tools_dir.glob("*.yml"))
    if not yaml_files:
        print(f"Warning: No YAML files found in {tools_dir}", file=sys.stderr)
        return toolsets, all_errors

    for yaml_file in yaml_files:
        try:
            data = yaml.safe_load(yaml_file.read_text())
        except yaml.YAMLError as e:
            all_errors.append(f"{yaml_file.name}: YAML parse error: {e}")
            continue

        if not isinstance(data, dict):
            all_errors.append(f"{yaml_file.name}: Expected a YAML mapping at root, got {type(data).__name__}")
            continue

        # Validate against schema
        if schema is not None:
            file_errors = validate_yaml_file(data, schema, yaml_file.name)
            all_errors.extend(file_errors)

        # Extract toolsets regardless of validation (still useful to see what's there)
        file_toolsets = data.get("toolsets", {})
        if not isinstance(file_toolsets, dict):
            continue

        # Build per-tool metadata lookup from the tools section
        file_tools = data.get("tools", {})
        tool_meta_lookup: dict[str, dict[str, Any]] = {}
        if isinstance(file_tools, dict):
            for tname, tdef in file_tools.items():
                if not isinstance(tdef, dict):
                    continue
                meta: dict[str, Any] = {}
                if "description" in tdef:
                    meta["description"] = tdef["description"]
                if "parameters" in tdef and isinstance(tdef["parameters"], list):
                    meta["parameters"] = tdef["parameters"]
                if meta:
                    tool_meta_lookup[tname] = meta

        for toolset_name, toolset_def in file_toolsets.items():
            if not isinstance(toolset_def, dict):
                continue

            tools_list = toolset_def.get("tools", [])
            # Filter out commented tools (strings starting with #)
            tools_list = [t for t in tools_list if isinstance(t, str) and not t.startswith("#")]

            entry: dict[str, Any] = {
                "tools": tools_list,
                "source": yaml_file.name,
            }
            if "title" in toolset_def:
                entry["title"] = toolset_def["title"]
            if "description" in toolset_def:
                entry["description"] = toolset_def["description"]

            # Attach per-tool metadata (description, parameters)
            tool_metadata = {t: tool_meta_lookup[t] for t in tools_list if t in tool_meta_lookup}
            if tool_metadata:
                entry["tool_metadata"] = tool_metadata

            if toolset_name in toolsets:
                all_errors.append(
                    f"{yaml_file.name}: Duplicate toolset '{toolset_name}' "
                    f"(first seen in {toolsets[toolset_name]['source']})"
                )

            toolsets[toolset_name] = entry

    return toolsets, all_errors


def main():
    parser = argparse.ArgumentParser(
        description="Parse and validate MCP tool YAML files into a consolidated JSON mapping"
    )
    parser.add_argument(
        "--tools-dir",
        type=Path,
        default=Path("tools"),
        help="Directory containing YAML tool files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tools/toolsets.json"),
        help="Output JSON file path",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="JSON schema file for validation",
    )
    parser.add_argument("--skip-validation", action="store_true", help="Skip JSON schema validation")
    args = parser.parse_args()

    if not args.tools_dir.is_dir():
        print(f"Error: {args.tools_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Load schema
    schema = None
    if not args.skip_validation:
        if args.schema.is_file():
            schema = json.loads(args.schema.read_text())
            print(f"Validating against schema: {args.schema}")
        else:
            print(
                f"Warning: Schema not found at {args.schema}, skipping validation",
                file=sys.stderr,
            )

    toolsets, errors = parse_yaml_tools(args.tools_dir, schema)

    # Report validation results
    if errors:
        print(f"\n{'=' * 60}", file=sys.stderr)
        print(f"VALIDATION ERRORS ({len(errors)}):", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)
    elif schema is not None:
        print("All YAML files passed schema validation")

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(toolsets, indent=2) + "\n")

    # Summary
    total_toolsets = len(toolsets)
    total_tools = sum(len(t["tools"]) for t in toolsets.values())
    sources = sorted(set(t["source"] for t in toolsets.values()))

    print(f"\nParsed {len(sources)} YAML files -> {total_toolsets} toolsets, {total_tools} tool references")
    print(f"Output: {args.output}")

    for name, info in toolsets.items():
        print(f"  {name}: {len(info['tools'])} tools ({info['source']})")

    # Exit with error code if validation failed
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
