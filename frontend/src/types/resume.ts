export type ResumeAnalysisStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface ResumeUploadAnalysis {
  status: ResumeAnalysisStatus;
  errorMessage?: string;
}

export interface UploadResponse {
  storage: { resumeId: string };
  resumeId: string;
  status: ResumeAnalysisStatus;
  analysis?: ResumeUploadAnalysis;
}
