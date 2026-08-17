export type ResumeAnalysisStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface ResumeUploadAnalysis {
  originalText: string;
  status: ResumeAnalysisStatus;
  analysisId: number;
}

export interface UploadResponse {
  analysis: ResumeUploadAnalysis;
  storage: { resumeId: string };
  duplicate: boolean;
}
