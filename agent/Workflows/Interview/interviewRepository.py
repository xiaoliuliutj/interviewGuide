"""面试工作流的 PostgreSQL 持久化，实现状态、回合和 run 结果的原子提交。"""

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from agent.Common.Exceptions.AgentException import (
    AgentSessionConcurrencyError,
    AgentSessionNotFoundError,
    AgentSessionStateError,
    MemoryVersionConflictError,
)
from agent.Common.Postgres.PostgresService import PostgresService
from agent.WorkFlows.Interview.interviewModels import InterviewSessionState, InterviewTurn


class InterviewWorkflowRepository:
    """在单个数据库事务中提交面试状态、短期记忆消息、回合记录和幂等结果。"""

    def __init__(self, postgresService: PostgresService) -> None:
        """保存统一的 PostgreSQL 服务，避免工作流自行创建连接池。"""
        self.postgresService = postgresService

    async def loadState(self, sessionId: str, userId: str) -> InterviewSessionState | None:
        """按会话和用户读取权威面试状态，跨用户访问直接视为不存在。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT state_json FROM agent_interview_workflow WHERE session_id=$1 AND user_id=$2",
                sessionId,
                userId,
            )
        if row is None:
            return None
        return InterviewSessionState.model_validate(row["state_json"])

    async def loadRunResult(self, runId: str, sessionId: str, userId: str) -> dict[str, Any] | None:
        """读取同一 runId 的已完成结果，网络重试时禁止重复调用大模型。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT status,result_json FROM agent_run WHERE run_id=$1 AND session_id=$2 AND user_id=$3",
                runId,
                sessionId,
                userId,
            )
        if row is None or row["status"] == "PROCESSING" or row["result_json"] is None:
            return None
        return dict(row["result_json"])

    async def ensureSession(self, sessionId: str, userId: str, resumeId: str | None) -> None:
        """创建或校验通用 Agent 会话归属，为首次面试初始化提供稳定起点。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetchval(
                    "INSERT INTO agent_session(session_id,user_id,resume_id,status) VALUES($1,$2,$3,'ACTIVE') "
                    "ON CONFLICT(session_id) DO NOTHING RETURNING session_id",
                    sessionId,
                    userId,
                    resumeId,
                )
                if inserted is not None:
                    return
                session = await connection.fetchrow(
                    "SELECT user_id,resume_id,deleted_at FROM agent_session WHERE session_id=$1 FOR UPDATE",
                    sessionId,
                )
                if session is None or session["deleted_at"] is not None:
                    raise AgentSessionNotFoundError("会话不存在或已删除")
                if session["user_id"] != userId:
                    raise AgentSessionStateError("会话不属于当前调用主体")
                await connection.execute(
                    "UPDATE agent_session SET resume_id=COALESCE($2,resume_id),updated_at=CURRENT_TIMESTAMP WHERE session_id=$1",
                    sessionId,
                    resumeId,
                )

    async def claimRun(self, sessionId: str, userId: str, runId: str, expectedVersion: int) -> str:
        """原子占用面试会话，保证不同 runId 不能并发推进同一份状态。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    "SELECT session_id,user_id,status FROM agent_run WHERE run_id=$1 FOR UPDATE",
                    runId,
                )
                if existing is not None:
                    if existing["session_id"] != sessionId or existing["user_id"] != userId:
                        raise AgentSessionConcurrencyError("runId 已绑定其他会话或主体")
                    return f"EXISTING_{existing['status']}"
                claimed = await connection.fetchval(
                    "UPDATE agent_session SET active_run_id=$2,active_run_heartbeat_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP "
                    "WHERE session_id=$1 AND user_id=$3 AND state_version=$4 AND deleted_at IS NULL "
                    "AND (active_run_id IS NULL OR active_run_heartbeat_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes') "
                    "RETURNING session_id",
                    sessionId,
                    runId,
                    userId,
                    expectedVersion,
                )
                if claimed is None:
                    raise MemoryVersionConflictError("会话版本已变化或已有任务正在执行")
                await connection.execute(
                    "INSERT INTO agent_run(run_id,session_id,user_id,task_type,expected_state_version,status) "
                    "VALUES($1,$2,$3,'INTERVIEW_WORKFLOW',$4,'PROCESSING')",
                    runId,
                    sessionId,
                    userId,
                    expectedVersion,
                )
        return "PROCESSING"

    async def commitState(
        self,
        state: InterviewSessionState,
        runId: str,
        expectedVersion: int,
        responseJson: str,
        userContent: str | None = None,
        assistantContent: str | None = None,
        turn: InterviewTurn | None = None,
    ) -> None:
        """原子保存新状态、消息、回合和成功结果，避免半轮面试被外部读取。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                updated = await connection.fetchval(
                    "UPDATE agent_session SET state_version=$4,active_run_id=NULL,active_run_heartbeat_at=NULL,status=$5,updated_at=CURRENT_TIMESTAMP "
                    "WHERE session_id=$1 AND user_id=$2 AND active_run_id=$3 AND state_version=$6 AND deleted_at IS NULL RETURNING session_id",
                    state.sessionId,
                    state.userId,
                    runId,
                    state.stateVersion,
                    state.status.value,
                    expectedVersion,
                )
                if updated is None:
                    raise MemoryVersionConflictError("会话版本或执行权已失效，拒绝提交过期结果")
                stateJson = state.model_dump(mode="json")
                await connection.execute(
                    "INSERT INTO agent_interview_workflow(session_id,user_id,status,current_stage,current_topic,state_json,last_activity_at,deadline_at) "
                    "VALUES($1,$2,$3,$4,$5,$6::jsonb,$7,$8) "
                    "ON CONFLICT(session_id) DO UPDATE SET status=EXCLUDED.status,current_stage=EXCLUDED.current_stage,"
                    "current_topic=EXCLUDED.current_topic,state_json=EXCLUDED.state_json,last_activity_at=EXCLUDED.last_activity_at,"
                    "deadline_at=EXCLUDED.deadline_at,updated_at=CURRENT_TIMESTAMP",
                    state.sessionId,
                    state.userId,
                    state.status.value,
                    state.currentStage.value,
                    state.currentTopic,
                    json.dumps(stateJson, ensure_ascii=False),
                    state.lastActivityAt,
                    state.deadlineAt,
                )
                if turn is not None:
                    await connection.execute(
                        "INSERT INTO agent_interview_workflow_turn(turn_id,session_id,run_id,stage,topic,question,answer_masked,evaluation_json,action) "
                        "VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)",
                        uuid4(),
                        state.sessionId,
                        runId,
                        turn.stage.value,
                        turn.topic,
                        turn.question,
                        turn.answer,
                        json.dumps(turn.evaluation.model_dump(mode="json"), ensure_ascii=False),
                        turn.action.value,
                    )
                if userContent is not None or assistantContent is not None:
                    nextSequence = await connection.fetchval(
                        "SELECT COALESCE(MAX(sequence_number),0) FROM agent_session_message WHERE session_id=$1",
                        state.sessionId,
                    )
                    for offset, role, content in (
                        (1, "user", userContent),
                        (2, "assistant", assistantContent),
                    ):
                        if content is None:
                            continue
                        await connection.execute(
                            "INSERT INTO agent_session_message(session_id,run_id,turn_number,sequence_number,role,content_masked,content_hash) "
                            "VALUES($1,$2,$3,$4,$5,$6,$7)",
                            state.sessionId,
                            runId,
                            (nextSequence // 2) + 1,
                            nextSequence + offset,
                            role,
                            content,
                            hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        )
                await connection.execute(
                    "UPDATE agent_run SET status='COMPLETED',result_json=$2::jsonb,completed_at=CURRENT_TIMESTAMP "
                    "WHERE run_id=$1 AND status='PROCESSING'",
                    runId,
                    responseJson,
                )

    async def failRun(self, sessionId: str, runId: str, responseJson: str) -> None:
        """失败时释放执行权并保存失败响应，确保调用方重试不会卡住会话。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "UPDATE agent_session SET active_run_id=NULL,active_run_heartbeat_at=NULL,updated_at=CURRENT_TIMESTAMP "
                    "WHERE session_id=$1 AND active_run_id=$2",
                    sessionId,
                    runId,
                )
                await connection.execute(
                    "UPDATE agent_run SET status='FAILED',result_json=$2::jsonb,completed_at=CURRENT_TIMESTAMP "
                    "WHERE run_id=$1 AND status='PROCESSING'",
                    runId,
                    responseJson,
                )

    async def deleteSession(self, sessionId: str, userId: str) -> bool:
        """物理删除已关闭面试的 Workflow、消息、运行记录与会话本体，确保关闭后不会在历史中保留。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                session = await connection.fetchrow(
                    "SELECT active_run_id,active_run_heartbeat_at FROM agent_session WHERE session_id=$1 AND user_id=$2 FOR UPDATE",
                    sessionId,
                    userId,
                )
                if session is None:
                    return False
                if session["active_run_id"] is not None and session["active_run_heartbeat_at"] is not None:
                    active = await connection.fetchval(
                        "SELECT active_run_heartbeat_at >= CURRENT_TIMESTAMP - INTERVAL '5 minutes' "
                        "FROM agent_session WHERE session_id=$1",
                        sessionId,
                    )
                    if active:
                        raise AgentSessionConcurrencyError("当前面试回合仍在执行，暂时不能关闭会话")
                await connection.execute("DELETE FROM agent_rag_retrieval_source WHERE session_id=$1", sessionId)
                await connection.execute("DELETE FROM agent_interview_workflow_turn WHERE session_id=$1", sessionId)
                await connection.execute("DELETE FROM agent_interview_workflow WHERE session_id=$1", sessionId)
                await connection.execute("DELETE FROM agent_session_message WHERE session_id=$1", sessionId)
                await connection.execute("DELETE FROM agent_session_summary WHERE session_id=$1", sessionId)
                await connection.execute("DELETE FROM agent_interview_memory WHERE session_id=$1", sessionId)
                await connection.execute(
                    "DELETE FROM agent_outbox_event WHERE aggregate_id=$1 AND event_type='SESSION_SUMMARY_RETRY'",
                    sessionId,
                )
                await connection.execute("DELETE FROM agent_run WHERE session_id=$1", sessionId)
                await connection.execute("DELETE FROM agent_session WHERE session_id=$1 AND user_id=$2", sessionId, userId)
                return True

    async def loadExpiredSessions(self, inactiveSeconds: int) -> list[InterviewSessionState]:
        """查找长时间无活动的面试会话，供后台任务执行强制结束。"""
        pool = await self.postgresService.getPool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT state_json FROM agent_interview_workflow WHERE status IN ('ACTIVE','PAUSED') "
                "AND last_activity_at < CURRENT_TIMESTAMP - ($1 * INTERVAL '1 second')",
                inactiveSeconds,
            )
        return [InterviewSessionState.model_validate(row["state_json"]) for row in rows]
