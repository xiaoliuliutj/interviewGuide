"""负责简历文件解析、异步 LLM 评估、状态查询和长期记忆写入。"""

import base64
import logging
from typing import Any

from agent.Common.Exceptions.AgentException import AgentRequestContractError, RagDocumentParseError
from agent.Common.AgentResults import AgentError, AgentOperationResponse, AgentResultStatus
from agent.LLM.llmService import LlmService
from agent.Memory.memoryService import MemoryService
from agent.Common.PromptService import PromptLoader
from agent.RAG.ragDocumentParser import DocumentParser
from agent.RAG.ragPolicy import RagPolicy
from agent.Workflows.Resume.resumeModels import ResumeEvaluation, ResumeJobStatus
from agent.LLM.structuredOutput import StructuredOutputInvoker
from agent.Workflows.Resume.resumeRepository import ResumeWorkflowRepository
from agent.Common.AgentRequest import AgentOperationRequest
import json


logger = logging.getLogger(__name__)


class ResumeWorkflow:
    """将确定性文本提取和 LLM 评估拆成可重试的异步任务链。"""

    def __init__(
        self,
        llmService: LlmService,
        memoryService: MemoryService,
        repository: ResumeWorkflowRepository,
        promptLoader: PromptLoader | None = None,
    ) -> None:
        """注入共享 LLM、记忆和数据库适配器，保证评估结果进入既有长期记忆。"""
        self.llmService = llmService
        self.memoryService = memoryService
        self.repository = repository
        self.promptLoader = promptLoader or PromptLoader()
        self.structuredOutput = StructuredOutputInvoker(llmService, self.promptLoader)
        self.parser = DocumentParser(RagPolicy())

    async def handleRequest(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """识别自然语言简历请求并返回已完成结果、处理中状态或缺少简历的明确错误。"""
        payload = request.payload
        if payload.get("fileContent") or payload.get("documentContent"):
            return await self.upload(request)
        jobRunIdValue = payload.get("resumeRunId")
        jobRunId = jobRunIdValue.strip() if isinstance(jobRunIdValue, str) and jobRunIdValue.strip() else None
        if jobRunId is not None:
            job = await self.repository.loadJob(jobRunId, request.context.principal_id)
            if job is None:
                raise AgentRequestContractError("简历分析任务不存在或不属于当前用户")
            jobStatus = str(job["job_status"])
            responseStatus = "COMPLETED" if jobStatus == "COMPLETED" else "FAILED" if jobStatus == "FAILED_FINAL" else "PROCESSING"
            responseCode = AgentResultStatus.RESUME_ANALYSIS_FAILED if responseStatus == "FAILED" else AgentResultStatus.SUCCESS_WITH_DATA
            return self.buildResponse(request, responseStatus, {
                "type": "RESUME_ANALYSIS_STATUS",
                "resumeId": job["resume_id"],
                "status": jobStatus,
                "attemptCount": job["attempt_count"],
                "evaluation": job.get("evaluation_json"),
                "errorMessage": job.get("error_message"),
            }, responseCode)
        resumeIdValue = payload.get("resumeId")
        resumeId = resumeIdValue.strip() if isinstance(resumeIdValue, str) and resumeIdValue.strip() else None
        latest = await self.repository.loadLatestEvaluation(request.context.principal_id, resumeId)
        if latest is None:
            raise AgentRequestContractError("当前用户没有可供分析的简历")
        if latest["status"] == "COMPLETED" and latest.get("evaluation_json") is not None:
            return self.buildResponse(request, "COMPLETED", {
                "type": "RESUME_EVALUATION",
                "resumeId": latest["resume_id"],
                "evaluation": latest["evaluation_json"],
            }, AgentResultStatus.SUCCESS_WITH_DATA)
        if latest["status"] == "FAILED":
            return self.buildResponse(request, "FAILED", {
                "type": "RESUME_ANALYSIS",
                "resumeId": latest["resume_id"],
                "status": latest["status"],
                "errorMessage": latest.get("error_message"),
            }, AgentResultStatus.RESUME_ANALYSIS_FAILED)
        return self.buildResponse(request, "PROCESSING", {
            "type": "RESUME_ANALYSIS",
            "resumeId": latest["resume_id"],
            "status": latest["status"],
            "message": "简历正在解析或评估，请稍后查询。",
        }, AgentResultStatus.SUCCESS_WITH_DATA)

    async def upload(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """校验并保存文件后立即返回 PENDING，真正解析和 LLM 评估由后台 worker 执行。"""
        payload = request.payload
        resumeId = self.requireString(payload, "resumeId")
        raw = payload.get("fileContent") or payload.get("documentContent")
        if not isinstance(raw, str) or not raw.strip():
            raise AgentRequestContractError("简历文件内容不能为空")
        try:
            content = base64.b64decode(raw) if payload.get("contentEncoding") == "base64" else raw.encode("utf-8")
        except Exception as error:
            raise AgentRequestContractError("简历文件编码无效") from error
        if len(content) > RagPolicy().maxDocumentBytes:
            raise AgentRequestContractError("简历文件超过允许的大小限制")
        result = await self.repository.saveUpload(
            resumeId,
            request.context.principal_id,
            self.requireString(payload, "fileName"),
            (payload["contentType"].strip() if isinstance(payload.get("contentType"), str)
             and payload["contentType"].strip() else None),
            content,
            (payload["targetRole"].strip() if isinstance(payload.get("targetRole"), str)
             and payload["targetRole"].strip() else None),
            request.context.run_id,
            request.context.conversation_id,
        )
        return self.buildResponse(request, "PROCESSING", {
            "type": "RESUME_ANALYSIS",
            **result,
        }, AgentResultStatus.SUCCESS_WITH_DATA)

    async def processJobs(self) -> None:
        """领取并完成后台简历任务，解析失败或模型失败均按三次总尝试处理。"""
        for job in await self.repository.claimJobs():
            try:
                document = await self.repository.loadDocument(str(job["resume_id"]), str(job["user_id"]))
                if document is None:
                    raise AgentRequestContractError("简历原文不存在")
                sections = self.parser.parse(
                    document["raw_content"],
                    str(document["file_name"]),
                    document.get("content_type"),
                )
                extractedText = "\n\n".join(item.content for item in sections).strip()
                if not extractedText:
                    raise RagDocumentParseError("简历未提取到有效文本")
                await self.repository.markAnalyzing(str(job["resume_id"]), extractedText)
                evaluation = await self.evaluate(
                    str(job["resume_id"]),
                    extractedText,
                    str(job.get("target_role") or "通用技术岗位"),
                )
                await self.repository.completeJob(str(job["run_id"]), str(job["resume_id"]), evaluation)
                try:
                    await self.memoryService.saveResumeEvaluation(
                        str(job["user_id"]),
                        str(job["resume_id"]),
                        evaluation.model_dump(mode="json"),
                    )
                except Exception:
                    # 简历评估已持久化完成，长期记忆写入失败不能把已完成的分析任务回滚为失败。
                    logger.exception("简历长期记忆写入失败，resumeId=%s", job["resume_id"])
            except Exception as error:
                logger.exception("简历解析或评估任务失败，resumeId=%s", job["resume_id"])
                attemptCount = int(job.get("attempt_count") or 0) + 1
                await self.repository.failJob(
                    str(job["run_id"]),
                    str(job["resume_id"]),
                    str(error),
                    attemptCount >= 3,
                )

    async def reanalyze(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """对已有简历重建异步评估任务，Java 无需取得 Agent 保存的原始文件。"""
        payload = request.payload
        result = await self.repository.recreateJob(
            self.requireString(payload, "resumeId"),
            request.context.principal_id,
            self.requireString(payload, "targetRole"),
            request.context.run_id,
            request.context.conversation_id,
        )
        return self.buildResponse(request, "PROCESSING", {"type": "RESUME_ANALYSIS", **result}, AgentResultStatus.SUCCESS_WITH_DATA)

    async def download(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """读取原始简历并以 Base64 传递给调用方，避免 Agent 文件系统对外暴露。"""
        document = await self.repository.downloadDocument(
            self.requireString(request.payload, "resumeId"), request.context.principal_id
        )
        if document is None:
            raise AgentRequestContractError("简历不存在或不属于当前用户")
        return self.buildResponse(request, "COMPLETED", {
            "fileName": document["file_name"],
            "contentType": document["content_type"],
            "content": base64.b64encode(document["raw_content"]).decode("ascii"),
        }, AgentResultStatus.SUCCESS_WITH_DATA)

    async def delete(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """删除简历原文、任务和长期记忆；重复调用保持幂等成功。"""
        await self.repository.deleteResume(
            self.requireString(request.payload, "resumeId"), request.context.principal_id
        )
        return self.buildResponse(request, "COMPLETED", None, AgentResultStatus.SUCCESS_WITHOUT_DATA)

    async def evaluate(self, resumeId: str, text: str, targetRole: str) -> ResumeEvaluation:
        """调用外置简历评估提示词并严格校验六项评分和结构化评估字段。"""
        return await self.structuredOutput.invoke(
            schema=ResumeEvaluation,
            businessPrompt=self.promptLoader.loadPrompt("Resume/resumeAnalysis.txt"),
            inputPayload={"resumeId": resumeId, "targetRole": targetRole, "resumeText": text},
        )

    def buildResponse(
        self,
        request: AgentOperationRequest,
        status: str,
        data: dict[str, object] | None,
        statusCode: AgentResultStatus,
    ) -> AgentOperationResponse:
        """构建统一外层响应，简历业务差异全部封装在 data 内。"""
        return AgentOperationResponse(
            api_version=request.context.api_version,
            request_id=request.context.request_id,
            run_id=request.context.run_id,
            principal_id=request.context.principal_id,
            conversation_id=request.context.conversation_id,
            status_code=statusCode,
            status=status,
            state_version=request.state_version,
            data=data,
        )

    def requireString(self, payload: dict[str, object], field: str) -> str:
        """读取简历上传所需字段并拒绝空值，避免后台任务创建后才发现请求不完整。"""
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AgentRequestContractError(f"data.{field} is required")
        return value.strip()
