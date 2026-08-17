from pathlib import Path

from agent.Common.Exceptions.agent_exception import PromptNotFoundError


class PromptLoader:
    """从 Prompts 目录加载受版本控制的提示词文件。"""

    def __init__(self) -> None:
        """确定提示词根目录，避免业务模块自行拼接磁盘路径。"""
        self.promptRoot = Path(__file__).resolve().parent

    def loadPrompt(self, relativePath: str, **parameters: str) -> str:
        """读取提示词并替换命名参数，缺少文件时返回明确的领域异常。"""
        promptPath = self.promptRoot / relativePath
        if not promptPath.is_file():
            raise PromptNotFoundError(f"提示词文件不存在：{relativePath}")
        content = promptPath.read_text(encoding="utf-8")
        try:
            return content.format(**parameters)
        except KeyError as error:
            raise PromptNotFoundError(f"提示词参数缺失：{error.args[0]}") from error
