from agent.Common.AgentModels import SkillDefinition
from agent.Common.AgentResults import AgentTaskType
from agent.Common.PromptService import PromptLoader


class SkillService:
    """加载已注册技能及其可调用工具范围。"""

    def __init__(self, promptLoader: PromptLoader | None = None) -> None:
        """使用统一加载器读取 Skills 目录中的定义文件。"""
        self.promptLoader = promptLoader or PromptLoader()

    async def resolveSkill(self, taskType: AgentTaskType) -> SkillDefinition:
        """按照内部任务类型提供系统提示词和工具授权范围。"""
        definitions = {
            AgentTaskType.CONVERSATION: ("skillConversation.txt", ("fetchWebPage",), True, True),
            AgentTaskType.INTERVIEW_TURN: ("skillInterviewTurn.txt", (), True, True),
            AgentTaskType.RESUME_ANALYSIS: ("skillResumeAnalysis.txt", (), True, True),
            AgentTaskType.RAG_DOCUMENT_INDEXING: ("skillRagDocumentIndexing.txt", ("parseDocument",), False, False),
            AgentTaskType.WEB_PAGE_FETCH: ("skillWebPageFetch.txt", ("fetchWebPage",), False, False),
            AgentTaskType.WEBSITE_CRAWL: ("skillWebsiteCrawl.txt", ("crawlWebPages",), False, False),
        }
        filename, allowedTools, memoryEnabled, ragEnabled = definitions.get(
            taskType, ("skillDefaultTask.txt", (), False, False)
        )
        return SkillDefinition(
            taskType=taskType,
            systemPrompt=self.promptLoader.loadSkill(filename),
            allowedToolNames=allowedTools,
            memoryEnabled=memoryEnabled,
            ragEnabled=ragEnabled,
        )
