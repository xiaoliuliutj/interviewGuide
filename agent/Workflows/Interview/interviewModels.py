"""面试工作流的状态、计划和结构化模型输出定义。"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InterviewStage(StrEnum):
    """定义面试必须按顺序推进的六个阶段。"""

    OPENING = "OPENING"
    PROJECT = "PROJECT"
    FUNDAMENTAL = "FUNDAMENTAL"
    SCENARIO = "SCENARIO"
    CODING = "CODING"
    SUMMARY = "SUMMARY"


class InterviewStatus(StrEnum):
    """定义 Agent 侧面试会话的可持久化生命周期状态。"""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    AUTO_TERMINATED = "AUTO_TERMINATED"
    FAILED = "FAILED"


class InterviewAction(StrEnum):
    """限定回答评估后允许执行的下一步动作。"""

    FOLLOW_UP = "FOLLOW_UP"
    NEXT_QUESTION = "NEXT_QUESTION"
    NEXT_STAGE = "NEXT_STAGE"
    END_INTERVIEW = "END_INTERVIEW"


class InterviewIntent(StrEnum):
    """限定自然语言在面试会话中可触发的控制意图。"""

    START_INTERVIEW = "START_INTERVIEW"
    SUBMIT_ANSWER = "SUBMIT_ANSWER"
    PAUSE_INTERVIEW = "PAUSE_INTERVIEW"
    RESUME_INTERVIEW = "RESUME_INTERVIEW"
    COMPLETE_INTERVIEW = "COMPLETE_INTERVIEW"
    QUERY_PROGRESS = "QUERY_PROGRESS"


class InterviewPlanStage(BaseModel):
    """描述单个阶段的题目范围和硬性预算，不预生成具体问题。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    stage: InterviewStage
    topics: list[str] = Field(default_factory=list, max_length=12)
    difficulty: Literal["EASY", "MEDIUM", "HARD"]
    maxPrimaryQuestions: int = Field(ge=0, le=4)
    maxFollowupsPerQuestion: int = Field(ge=0, le=2)
    timeBudgetMinutes: int = Field(ge=0, le=60)


class InterviewPlan(BaseModel):
    """保存一次面试的稳定计划，防止每轮模型调用重新规划面试。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    candidateSummary: str = Field(min_length=1, max_length=2000)
    strategySummary: str = Field(min_length=1, max_length=2000)
    stages: list[InterviewPlanStage] = Field(min_length=6, max_length=6)
    selectedSkills: list[str] = Field(default_factory=list, max_length=4)
    coverageMatrix: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validatePlan(self) -> "InterviewPlan":
        """校验六阶段顺序和固定阶段约束，避免模型返回无法执行的计划。"""
        if [item.stage for item in self.stages] != list(InterviewStage):
            raise ValueError("面试计划必须按六个固定阶段完整配置")
        stageMap = {item.stage: item for item in self.stages}
        if stageMap[InterviewStage.OPENING].maxPrimaryQuestions != 1:
            raise ValueError("OPENING 阶段必须只有一个主问题")
        if stageMap[InterviewStage.OPENING].maxFollowupsPerQuestion != 0:
            raise ValueError("OPENING 阶段不允许追问")
        if stageMap[InterviewStage.SUMMARY].maxPrimaryQuestions != 1:
            raise ValueError("SUMMARY 阶段必须只保留一次总结输出")
        if stageMap[InterviewStage.SUMMARY].maxFollowupsPerQuestion != 0:
            raise ValueError("SUMMARY 阶段不允许追问")
        if stageMap[InterviewStage.CODING].maxFollowupsPerQuestion != 0:
            raise ValueError("CODING 阶段不允许普通追问")
        return self

    def getStage(self, stage: InterviewStage) -> InterviewPlanStage:
        """返回指定阶段的稳定计划，供路由和题量策略使用。"""
        return next(item for item in self.stages if item.stage == stage)


class InterviewEvaluation(BaseModel):
    """描述当前回答质量，评价节点不能直接决定流程跳转。"""

    model_config = ConfigDict(extra="forbid")

    evaluationSummary: str = Field(min_length=1, max_length=500)
    score: int = Field(ge=0, le=100)
    answerSummary: str = Field(min_length=1, max_length=1000)
    strengths: list[str] = Field(default_factory=list, max_length=10)
    weaknesses: list[str] = Field(default_factory=list, max_length=10)


class InterviewRoute(BaseModel):
    """描述受限路由节点建议的动作和下一题抽象主题。"""

    model_config = ConfigDict(extra="forbid")

    action: InterviewAction
    nextTopic: str | None = Field(default=None, min_length=1, max_length=300)


class InterviewQuestion(BaseModel):
    """定义问题生成节点的唯一输出，避免其混入评分或流程字段。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1200)


class InterviewSummary(BaseModel):
    """定义面试结束时可展示且可写入长期记忆的最终评价。"""

    model_config = ConfigDict(extra="forbid")

    overallScore: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list, max_length=10)
    weaknesses: list[str] = Field(default_factory=list, max_length=10)
    suggestions: list[str] = Field(default_factory=list, max_length=10)


class InterviewTurn(BaseModel):
    """持久化一轮已被状态机接受的问答、评价和路由结果。"""

    turnId: str
    runId: str
    stage: InterviewStage
    topic: str | None
    question: str
    answer: str
    evaluation: InterviewEvaluation
    action: InterviewAction
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class InterviewSessionState(BaseModel):
    """保存面试流程的权威状态，Java 只读取其响应投影而不参与推进。"""

    model_config = ConfigDict(populate_by_name=True)

    sessionId: str
    userId: str
    resumeId: str | None = None
    targetRole: str = "通用技术岗位"
    difficulty: Literal["EASY", "MEDIUM", "HARD"] = "MEDIUM"
    status: InterviewStatus = InterviewStatus.ACTIVE
    currentStage: InterviewStage = InterviewStage.OPENING
    currentTopic: str | None = None
    currentQuestion: str | None = None
    plan: InterviewPlan
    stateVersion: int = Field(default=0, ge=0)
    primaryQuestionCount: int = Field(default=0, ge=0)
    totalPrimaryQuestionCount: int = Field(default=0, ge=0)
    followupCount: int = Field(default=0, ge=0)
    totalQuestionCount: int = Field(default=0, ge=0, le=20)
    stageQuestionCounts: dict[str, int] = Field(default_factory=dict)
    topicQuestionCounts: dict[str, int] = Field(default_factory=dict)
    askedQuestionCatalog: list[str] = Field(default_factory=list, max_length=20)
    currentQuestionEvidence: list[str] = Field(default_factory=list, max_length=8)
    turns: list[InterviewTurn] = Field(default_factory=list, max_length=20)
    finalEvaluation: InterviewSummary | None = None
    lastActivityAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadlineAt: datetime | None = None


class WorkflowIntentDecision(BaseModel):
    """限定顶层自然语言路由输出，禁止模型返回任意代码路径。"""

    model_config = ConfigDict(extra="forbid")

    workflow: Literal["INTERVIEW", "RESUME_ANALYSIS", "GENERAL_CONVERSATION"]
    intent: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)


class InterviewIntentDecision(BaseModel):
    """限定会话内控制意图，普通回答默认进入回答评估流程。"""

    model_config = ConfigDict(extra="forbid")

    intent: InterviewIntent
    confidence: float = Field(ge=0, le=1)
