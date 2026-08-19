"""Java 提供的输出 Schema 的通用 JSON 解析、校验和格式诊断。"""

import json
from typing import Any


class OutputSchemaValidationError(ValueError):
    """模型 JSON 不满足调用方提供的业务 Schema。"""


def parseJsonObject(content: str) -> dict[str, Any]:
    """接受纯 JSON 或完整 Markdown JSON 代码块，但拒绝说明文字和非对象根节点。"""
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise OutputSchemaValidationError("模型输出根节点必须是 JSON 对象")
    return payload


def validateOutput(payload: dict[str, Any], schema: dict[str, Any] | None) -> None:
    """校验受限 JSON Schema；业务规则由 Java Schema 描述而非 Agent 内置。"""
    if schema is not None:
        _validate(payload, schema, "$")


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise OutputSchemaValidationError(f"{path} 必须是对象")
        required = schema.get("required", [])
        if not isinstance(required, list):
            raise OutputSchemaValidationError("Schema.required 必须是数组")
        for field in required:
            if not isinstance(field, str) or field not in value:
                raise OutputSchemaValidationError(f"{path}.{field} 是必填字段")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise OutputSchemaValidationError("Schema.properties 必须是对象")
        if schema.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                raise OutputSchemaValidationError(f"{path} 包含未定义字段: {', '.join(sorted(extras))}")
        for key, child in properties.items():
            if key in value and isinstance(child, dict):
                _validate(value[key], child, f"{path}.{key}")
    elif expected == "array":
        if not isinstance(value, list):
            raise OutputSchemaValidationError(f"{path} 必须是数组")
        _validateLength(value, schema, path)
        itemSchema = schema.get("items")
        if isinstance(itemSchema, dict):
            for index, item in enumerate(value):
                _validate(item, itemSchema, f"{path}[{index}]")
    elif expected == "string":
        if not isinstance(value, str):
            raise OutputSchemaValidationError(f"{path} 必须是字符串")
        _validateLength(value, schema, path)
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise OutputSchemaValidationError(f"{path} 必须是整数")
        _validateNumber(value, schema, path)
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise OutputSchemaValidationError(f"{path} 必须是数值")
        _validateNumber(value, schema, path)
    elif expected == "boolean" and not isinstance(value, bool):
        raise OutputSchemaValidationError(f"{path} 必须是布尔值")
    if "enum" in schema and value not in schema["enum"]:
        raise OutputSchemaValidationError(f"{path} 必须是以下值之一: {schema['enum']}")


def _validateLength(value: str | list[Any], schema: dict[str, Any], path: str) -> None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        raise OutputSchemaValidationError(f"{path} 长度不能小于 {schema['minLength']}")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        raise OutputSchemaValidationError(f"{path} 长度不能大于 {schema['maxLength']}")
    if "minItems" in schema and len(value) < schema["minItems"]:
        raise OutputSchemaValidationError(f"{path} 项数不能小于 {schema['minItems']}")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        raise OutputSchemaValidationError(f"{path} 项数不能大于 {schema['maxItems']}")


def _validateNumber(value: int | float, schema: dict[str, Any], path: str) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        raise OutputSchemaValidationError(f"{path} 不能小于 {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        raise OutputSchemaValidationError(f"{path} 不能大于 {schema['maximum']}")
