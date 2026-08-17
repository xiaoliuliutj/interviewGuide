import { useState } from 'react';
import { resumeApi } from '../api/resume';
import { getErrorMessage } from '../api/request';
import FileUploadCard from '../components/FileUploadCard';

interface UploadPageProps { onUploadComplete: (resumeId: string) => void; }

export default function UploadPage({ onUploadComplete }: UploadPageProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [targetRole, setTargetRole] = useState('');

  const handleUpload = async (file: File) => {
    if (!targetRole.trim()) {
      setError('请先填写目标岗位');
      return;
    }
    setUploading(true);
    setError('');
    try {
      const data = await resumeApi.uploadAndAnalyze(file, targetRole.trim());
      if (!data.storage?.resumeId) throw new Error('上传未返回简历标识');
      onUploadComplete(data.storage.resumeId);
    } catch (error) {
      setError(getErrorMessage(error));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <section className="bg-white dark:bg-slate-800 rounded-xl p-5 border border-slate-200 dark:border-slate-700">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">目标岗位</label>
        <input value={targetRole} onChange={event => setTargetRole(event.target.value)}
          disabled={uploading} placeholder="例如：Java 后端实习生"
          className="w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500" />
      </section>
      <FileUploadCard title="开始你的 AI 模拟面试"
        subtitle="填写目标岗位并上传 PDF、Word 或文本简历，系统将异步完成解析与分析。"
        accept=".pdf,.doc,.docx,.txt" formatHint="支持 PDF, DOCX, TXT" maxSizeHint="最大 10MB"
        uploading={uploading} uploadButtonText="开始上传" selectButtonText="选择简历文件"
        error={error} onUpload={handleUpload} />
    </div>
  );
}
