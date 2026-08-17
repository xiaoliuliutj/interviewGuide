import { request } from './request';

export type AnalyzeStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface ResumeListItem {
  id: string;
  filename: string | null;
  fileSize: number;
  uploadedAt: string;
  latestScore: number | null;
  lastAnalyzedAt: string | null;
  interviewCount: number;
  analyzeStatus: AnalyzeStatus | null;
  analyzeError: string | null;
}

export interface AnalysisItem {
  id: number;
  overallScore: number;
  contentScore: number;
  structureScore: number;
  skillMatchScore: number;
  expressionScore: number;
  projectScore: number;
  summary: string;
  analyzedAt: string;
  strengths: string[];
  suggestions: string[];
  status: AnalyzeStatus;
  error: string | null;
}

export interface InterviewItem {
  sessionId: string;
  userId: string;
  candidateId: string;
  resumeId: string;
  jdId: string | null;
  interviewDirection: string | null;
  difficulty: string;
  totalQuestions: number;
  status: 'INITIALIZING' | 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'FAILED';
  stateVersion: number;
  currentQuestion: string | null;
  currentStage: string | null;
  issuedQuestionCount: number;
  primaryQuestionCount: number;
  totalPrimaryQuestionCount: number;
  followupCount: number;
  finalEvaluation: {
    overallScore?: number;
    summary?: string;
    strengths?: string[];
    weaknesses?: string[];
    suggestions?: string[];
  };
  createdAt: string;
  updatedAt: string;
}

export interface InterviewTurn {
  index: number;
  stage: string;
  question: string;
  answer: string | null;
  answeredAt: string | null;
  evaluationSummary: string | null;
  score: number | null;
}

export interface InterviewDetail { session: InterviewItem; turns: InterviewTurn[]; }

export interface ResumeDetail {
  id: string;
  filename: string | null;
  fileSize: number;
  contentType: string | null;
  uploadedAt: string;
  resumeText: string;
  analyses: AnalysisItem[];
  interviews: InterviewItem[];
}

export const historyApi = {
  getResumes: () => request.get<ResumeListItem[]>('/api/resumes'),
  getResumeDetail: (id: string | number) => request.get<ResumeDetail>(`/api/resumes/${id}/detail`),
  getInterviewDetail: (sessionId: string) => request.get<InterviewDetail>(`/api/interviews/${sessionId}`),
  async exportAnalysisPdf(resumeId: string | number): Promise<Blob> {
    const response = await request.getInstance().get(`/api/resumes/${resumeId}/export`, { responseType: 'blob', skipResultTransform: true } as never);
    return response.data;
  },
  async downloadResume(resumeId: string | number): Promise<Blob> {
    const response = await request.getInstance().get(`/api/resumes/${resumeId}/download`, { responseType: 'blob', skipResultTransform: true } as never);
    return response.data;
  },
  async exportInterviewPdf(sessionId: string): Promise<Blob> {
    const response = await request.getInstance().get(`/api/interviews/${sessionId}/export`, { responseType: 'blob', skipResultTransform: true } as never);
    return response.data;
  },
  deleteResume: (id: string | number) => request.delete<void>(`/api/resumes/${id}`),
  deleteInterview: (sessionId: string) => request.delete<void>(`/api/interviews/${sessionId}`),
  reanalyze: (id: string | number, targetRole: string) => request.post(`/api/resumes/${id}/reanalyze?targetRole=${encodeURIComponent(targetRole)}`),
};
