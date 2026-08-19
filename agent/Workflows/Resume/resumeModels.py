"""简历解析与异步评估工作流使用的结构化模型。"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResumeJobStatus(StrEnum):
    """定义简历异步任务的可查询状态。"""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    FAILED_FINAL = "FAILED_FINAL"


class ResumeIssue(BaseModel):
    """定义简历中一个可验证的问题及其改进建议。"""

    question: str = Field(min_length=1, max_length=500)
    priority: Literal["HIGH", "MEDIUM", "LOW"]
    suggestion: str = Field(min_length=1, max_length=1000)


class ResumeEvaluation(BaseModel):
    """复用参考项目的完整简历评估维度，所有结论必须基于已解析文本。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    overallScore: int = Field(ge=0, le=100)
    contentScore: int = Field(ge=0, le=100)
    structureScore: int = Field(ge=0, le=100)
    skillMatchScore: int = Field(ge=0, le=100)
    expressionScore: int = Field(ge=0, le=100)
    projectScore: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list, max_length=10)
    suggestions: list[str] = Field(default_factory=list, max_length=10)
    issues: list[ResumeIssue] = Field(default_factory=list, max_length=20)
    technicalStack: list[str] = Field(default_factory=list, max_length=30)
    technicalDepth: list[str] = Field(default_factory=list, max_length=20)
    careerPreferences: list[str] = Field(default_factory=list, max_length=20)
