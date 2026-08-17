import re
from typing import Any


class DataMasker:
    """在敏感数据进入模型、Redis、日志和长期记忆前统一执行脱敏。"""

    def maskText(self, content: str) -> str:
        """掩码手机号、邮箱、身份证号和中国大陆常见详细地址中的门牌号。"""
        content = re.sub(
            r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)",
            r"\1****\2",
            content,
        )
        content = re.sub(
            r"([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*)(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
            lambda match: f"{match.group(1)}***{match.group(3)}",
            content,
        )
        content = re.sub(
            r"(?<!\d)(\d{6})\d{8}(\d{3}[0-9Xx])(?!\d)",
            r"\1********\2",
            content,
        )
        return content

    def maskObject(self, value: Any) -> Any:
        """递归处理结构化评估结果，确保嵌套字符串不会绕过脱敏策略。"""
        if isinstance(value, str):
            return self.maskText(value)
        if isinstance(value, list):
            return [self.maskObject(item) for item in value]
        if isinstance(value, dict):
            return {key: self.maskObject(item) for key, item in value.items()}
        return value
