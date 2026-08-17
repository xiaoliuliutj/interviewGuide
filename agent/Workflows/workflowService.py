from typing import Any

from agent.Agents.AgentLoop import AgentLoop
from agent.LLM.llmService import LlmService
from agent.WorkFlows.Interview.interviewRepository import InterviewWorkflowRepository
from agent.WorkFlows.Interview.interviewWorkflow import InterviewWorkflow
from agent.WorkFlows.Resume.resumeRepository import ResumeWorkflowRepository
from agent.WorkFlows.Resume.resumeWorkflow import ResumeWorkflow
from agent.WorkFlows.workflowRuntime import WorkflowRuntime


class WorkflowService:
    """。"AgentLoop 。"API 提供统一 Workflow 服务入口。"""

    def __init__(
        self,
        llmService: LlmService,
        agentLoop: AgentLoop,
        interviewWorkflow: InterviewWorkflow,
        resumeWorkflow: ResumeWorkflow,
        interviewRepository: InterviewWorkflowRepository,
        resumeRepository: ResumeWorkflowRepository,
    ) -> None:
        """组装 WorkflowRuntime，统一承接自然语言路由和显式能力调用。"""
        self.runtime = WorkflowRuntime(
            llmService,
            agentLoop,
            interviewWorkflow,
            resumeWorkflow,
            interviewRepository,
            resumeRepository,
        )

    def __getattr__(self, name: str) -> Any:
        """。"Workflow 能力转交给对应运行时。"""
        return getattr(self.runtime, name)
