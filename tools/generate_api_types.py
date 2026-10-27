"""Generate Vue's JSDoc type source from the FastAPI OpenAPI schema."""

from pathlib import Path
import argparse
import json
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.main import app


OUTPUT = ROOT_DIR / "ui" / "src" / "types" / "api.generated.d.ts"
QUERY_TYPES = {
    "notes_list": "NotesListParams",
    "notes_search": "NotesSearchParams",
    "topics_summary": "TopicSummaryParams",
    "topics_export": "TopicExportParams",
}


def schema_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        result = name
    elif "anyOf" in schema or "oneOf" in schema:
        choices = schema.get("anyOf", schema.get("oneOf", []))
        result = " | ".join(sorted({schema_type(item) for item in choices})) or "unknown"
    elif "allOf" in schema:
        result = " & ".join(schema_type(item) for item in schema["allOf"]) or "unknown"
    elif "enum" in schema:
        result = " | ".join(repr(value) for value in schema["enum"])
    elif schema.get("type") == "array":
        item = schema_type(schema.get("items", {}))
        result = f"Array<{item}>"
    elif schema.get("type") == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        entries = [
            f"  {name}{'' if name in required else '?'}: {schema_type(value)};"
            for name, value in properties.items()
        ]
        additional = schema.get("additionalProperties")
        if additional is True:
            entries.append("  [key: string]: unknown;")
        elif isinstance(additional, dict):
            entries.append(f"  [key: string]: {schema_type(additional)};")
        result = "{\n" + "\n".join(entries) + "\n}" if entries else "Record<string, unknown>"
    else:
        result = {
            "string": "string",
            "integer": "number",
            "number": "number",
            "boolean": "boolean",
            "null": "null",
        }.get(schema.get("type"), "unknown")
    if schema.get("nullable") and "null" not in result:
        result = f"{result} | null"
    return result


def operation_ids(openapi: dict[str, Any]) -> list[str]:
    values = {
        operation["operationId"]
        for path_item in openapi.get("paths", {}).values()
        for operation in path_item.values()
        if isinstance(operation, dict) and operation.get("operationId")
    }
    return sorted(values)


def query_parameters(openapi: dict[str, Any], operation_id: str) -> list[dict[str, Any]]:
    for path_item in openapi.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or operation.get("operationId") != operation_id:
                continue
            return [parameter for parameter in operation.get("parameters", []) if parameter.get("in") == "query"]
    return []


def generate() -> str:
    openapi = app.openapi()
    schemas = openapi.get("components", {}).get("schemas", {})
    lines = [
        "/* Generated from FastAPI OpenAPI. Run `python tools/generate_api_types.py` to refresh. */",
        "",
    ]
    for name, schema in sorted(schemas.items()):
        lines.append(f"export type {name} = {schema_type(schema)};")
        lines.append("")
    for operation_id, type_name in QUERY_TYPES.items():
        parameters = query_parameters(openapi, operation_id)
        if not parameters:
            continue
        lines.append(f"export type {type_name} = {{")
        for parameter in parameters:
            name = json.dumps(parameter["name"], ensure_ascii=False)
            optional = "" if parameter.get("required") else "?"
            lines.append(f"  {name}{optional}: {schema_type(parameter.get('schema', {}))};")
        lines.extend(["};", ""])
    operations = " | ".join(repr(item) for item in operation_ids(openapi)) or "never"
    lines.append(f"export type ApiOperationId = {operations};")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate or verify Vue API types from FastAPI OpenAPI.")
    parser.add_argument("--check", action="store_true", help="Fail if generated types are stale; do not write files.")
    args = parser.parse_args()
    expected = generate()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            sys.stderr.write(f"Generated API types are stale: {OUTPUT.relative_to(ROOT_DIR).as_posix()}\n")
            raise SystemExit(1)
        print(f"API types are current: {OUTPUT.relative_to(ROOT_DIR).as_posix()}")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(expected, encoding="utf-8")
        print(OUTPUT.relative_to(ROOT_DIR).as_posix())
