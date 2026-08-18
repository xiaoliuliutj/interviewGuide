"""Agent 对外错误信息格式化。"""

from typing import Any


def formatValidationErrors(errors: list[dict[str, Any]]) -> str:
    """把 Pydantic 的结构化校验结果转换为前端可直接理解的中文错误说明。"""
    messages: list[str] = []
    for item in errors:
        location = ".".join(str(part) for part in item.get("loc", ())) or "request"
        errorType = str(item.get("type", ""))
        rawMessage = str(item.get("msg", "请求字段不合法"))
        if errorType in {"missing", "value_error.missing"}:
            message = "字段不能为空"
        elif errorType == "extra_forbidden":
            message = "包含协议未定义字段"
        elif errorType in {"string_type", "dict_type", "int_type"}:
            message = "字段类型不正确"
        else:
            message = rawMessage
        messages.append(f"{location}：{message}")
    return "；".join(messages) or "请求体不符合 Agent 协议"
