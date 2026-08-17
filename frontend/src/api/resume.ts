import { request } from './request';
import type { UploadResponse } from '../types/resume';

export const resumeApi = {
  /**
   * 上传简历并获取分析结果
   */
  async uploadAndAnalyze(file: File, targetRole: string): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('targetRole', targetRole);
    return request.upload<UploadResponse>('/api/resumes/upload', formData);
  },
};
