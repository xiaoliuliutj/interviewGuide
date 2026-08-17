from agent.Agents.models import SkillDefinition
from agent.Common.results import AgentTaskType
from agent.Prompts.prompt_loader import PromptLoader


class SkillService:
    """Provides task-specific prompts and capability permissions from the Skills module."""

    def __init__(self, promptLoader: PromptLoader | None = None) -> None:
        """注入提示词加载器，使任务规则不再散落在业务代码中。"""
        self.promptLoader = promptLoader or PromptLoader()

    async def resolveSkill(self, taskType: AgentTaskType) -> SkillDefinition:
        """Return the initial Skill definition for a supported Java task code."""
        configurations = {
            AgentTaskType.CONVERSATION: SkillDefinition(
                taskType=taskType,
                systemPrompt=self.promptLoader.loadPrompt("Skills/conversation.txt"),
                allowedToolNames=("loadMemory", "retrieveKnowledge", "getKnowledgeBaseStatus", "fetchWebPage"),
                memoryEnabled=True,
                ragEnabled=True,
            ),
            AgentTaskType.RESUME_ANALYSIS: SkillDefinition(
                taskType=taskType,
                systemPrompt=self.promptLoader.loadPrompt("Skills/resume_analysis.txt"),
                memoryEnabled=True,
                ragEnabled=True,
            ),
            AgentTaskType.INTERVIEW_TURN: SkillDefinition(
                taskType=taskType,
                systemPrompt=self.promptLoader.loadPrompt("Skills/interview_turn.txt"),
                allowedToolNames=("loadMemory", "retrieveKnowledge"),
                memoryEnabled=True,
                ragEnabled=True,
            ),
            AgentTaskType.RAG_DOCUMENT_INDEXING: SkillDefinition(
                taskType=taskType,
                systemPrompt=self.promptLoader.loadPrompt("Skills/rag_document_indexing.txt"),
            ),
            AgentTaskType.WEB_PAGE_FETCH: SkillDefinition(
                taskType=taskType,
                systemPrompt=self.promptLoader.loadPrompt("Skills/web_page_fetch.txt"),
                allowedToolNames=("fetchWebPage",),
            ),
            AgentTaskType.WEBSITE_CRAWL: SkillDefinition(
                taskType=taskType,
                systemPrompt=self.promptLoader.loadPrompt("Skills/website_crawl.txt"),
                allowedToolNames=("crawlWebPages",),
            ),
        }
        return configurations.get(taskType) or SkillDefinition(
            taskType=taskType,
            systemPrompt=self.promptLoader.loadPrompt("Skills/default_task.txt"),
        )
