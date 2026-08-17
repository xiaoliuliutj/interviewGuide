import { request } from './request';
import type { CreateInterviewRequest, InterviewQuestion, InterviewSession, SubmitAnswerRequest, SubmitAnswerResponse } from '../types/interview';

interface InterviewView {
  sessionId: string;
  resumeId: string;
  interviewDirection: string | null;
  difficulty: string;
  totalQuestions: number;
  status: InterviewSession['status'];
  stateVersion: number;
  currentQuestion: string | null;
  currentStage: string | null;
  issuedQuestionCount: number;
  primaryQuestionCount: number;
  totalPrimaryQuestionCount: number;
  followupCount: number;
  finalEvaluation: InterviewSession['finalEvaluation'];
  createdAt: string;
  updatedAt: string;
}

interface InterviewTurnView {
  index: number;
  stage: string;
  question: string;
  answer: string | null;
  evaluationSummary: string | null;
  score: number | null;
}

interface InterviewDetailView { session: InterviewView; turns: InterviewTurnView[]; }

function toQuestion(turn: InterviewTurnView): InterviewQuestion {
  return {
    questionIndex: turn.index, question: turn.question, type: 'AGENT', category: turn.stage,
    userAnswer: turn.answer, evaluationSummary: turn.evaluationSummary, score: turn.score,
  };
}

function toSession(view: InterviewView, turns: InterviewTurnView[] = []): InterviewSession {
  const questions = turns.map(toQuestion);
  if ((view.status === 'ACTIVE' || view.status === 'PAUSED') && view.currentQuestion) {
    questions.push({ questionIndex: questions.length, question: view.currentQuestion, type: 'AGENT', category: view.currentStage || 'UNKNOWN', userAnswer: null });
  }
  return {
    ...view,
    currentQuestionIndex: Math.max(0, questions.length - 1),
    questions,
  };
}

export interface TextSessionMeta extends InterviewView {}

export const interviewApi = {
  async listSessions(): Promise<TextSessionMeta[]> {
    return request.get<InterviewView[]>('/api/interviews');
  },

  async createSession(input: CreateInterviewRequest): Promise<InterviewSession> {
    const view = await request.post<InterviewView>('/api/interviews', {
      resumeId: input.resumeId,
      targetRole: input.targetRole,
      interviewDurationMinutes: input.interviewDurationMinutes,
      desiredDifficulty: input.difficulty,
      interviewDirection: input.interviewDirection ?? null,
      jdText: input.jdText ?? null,
      customCategories: input.customCategories,
    }, { timeout: 180000 });
    return toSession(view);
  },

  async getSession(sessionId: string): Promise<InterviewSession> {
    const detail = await request.get<InterviewDetailView>(`/api/interviews/${sessionId}`);
    return toSession(detail.session, detail.turns);
  },

  async submitAnswer(input: SubmitAnswerRequest): Promise<SubmitAnswerResponse> {
    const detail = await request.post<InterviewDetailView>(`/api/interviews/${input.sessionId}/answers`, {
      answer: input.answer,
      runId: input.runId,
    }, { timeout: 180000 });
    const session = toSession(detail.session, detail.turns);
    const nextQuestion = session.status === 'ACTIVE' && session.questions.length > 0
      ? session.questions[session.questions.length - 1] : null;
    return { session, hasNextQuestion: nextQuestion !== null, nextQuestion };
  },

  async getAgentStatus(sessionId: string): Promise<string> {
    const result = await request.get<{stage?: string}>(`/api/interviews/${sessionId}/agent-status`, {timeout: 5000});
    return result.stage || 'IDLE';
  },

  async completeInterview(sessionId: string): Promise<void> {
    await request.post<void>(`/api/interviews/${sessionId}/complete`);
  },

  async closeInterview(sessionId: string): Promise<void> {
    await request.delete<void>(`/api/interviews/${sessionId}`);
  },

  async pauseInterview(sessionId: string): Promise<void> {
    await request.post<void>(`/api/interviews/${sessionId}/pause`);
  },

  async findUnfinishedSession(resumeId?: string): Promise<InterviewSession | null> {
    const path = resumeId
      ? `/api/interviews/unfinished/${resumeId}`
      : '/api/interviews/unfinished';
    const view = await request.get<InterviewView | null>(path);
    return view ? toSession(view) : null;
  },
};
