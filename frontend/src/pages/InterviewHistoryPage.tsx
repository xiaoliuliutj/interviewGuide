import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, FileText, Loader2, PlayCircle, Trash2 } from 'lucide-react';

import { interviewApi, type TextSessionMeta } from '../api/interview';
import { historyApi } from '../api/history';
import { formatDateTime } from '../utils/date';
import DeleteConfirmDialog from '../components/DeleteConfirmDialog';

interface Props {
  onBack: () => void;
  onViewInterview: (sessionId: string, resumeId?: string) => void;
  onRestartInterview?: (resumeId: string) => void;
  onContinueInterview?: (sessionId: string) => void;
}

function isResumable(session: TextSessionMeta): boolean {
  return session.status === 'ACTIVE' || session.status === 'PAUSED';
}

export default function InterviewHistoryPage({
  onViewInterview,
  onRestartInterview,
  onContinueInterview,
}: Props) {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<TextSessionMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pendingDelete, setPendingDelete] = useState<TextSessionMeta | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSessions(await interviewApi.listSessions());
      setError('');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '加载文本面试记录失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await historyApi.deleteInterview(pendingDelete.sessionId);
      setSessions(current => current.filter(item => item.sessionId !== pendingDelete.sessionId));
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  };

  const exportPdf = async (sessionId: string) => {
    setExporting(sessionId);
    try {
      const blob = await historyApi.exportInterviewPdf(sessionId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `文本面试_${sessionId}.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(null);
    }
  };

  if (loading) {
    return <div className="flex min-h-[40vh] items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-primary-500" /></div>;
  }

  return (
    <main className="mx-auto max-w-5xl">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800 dark:text-white">文本面试记录</h1>
        <p className="mt-1 text-sm text-slate-500">只展示候选人可见的会话和问答内容。</p>
      </header>

      {error && <p className="mb-4 text-sm text-red-500">{error}</p>}

      {sessions.length === 0 ? (
        <div className="rounded-2xl bg-white p-12 text-center dark:bg-slate-800">
          <FileText className="mx-auto h-10 w-10 text-slate-400" />
          <p className="mt-3 text-slate-500">暂无文本面试记录。</p>
          <button onClick={() => navigate('/interview-hub')} className="mt-5 rounded-xl bg-primary-500 px-5 py-2.5 text-sm font-semibold text-white">开始面试</button>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map(session => (
            <article key={session.sessionId} className="flex items-center gap-4 rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-800">
              <FileText className="h-6 w-6 text-primary-500" />
              <div className="min-w-0 flex-1">
                <button onClick={() => onViewInterview(session.sessionId, session.resumeId)} className="font-medium text-slate-800 hover:text-primary-500 dark:text-white">
                  {session.interviewDirection ?? '通用'} · {session.difficulty}
                </button>
                <p className="mt-1 text-sm text-slate-500">{formatDateTime(session.createdAt)} · 已发出 {session.issuedQuestionCount} 题 · 动态上限 {session.totalQuestions} · {session.status}</p>
                {session.finalEvaluation?.summary && (
                  <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
                    面试评价：{session.finalEvaluation.summary}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1">
                {session.finalEvaluation?.overallScore != null && (
                  <span className="mr-2 rounded-full bg-primary-50 px-3 py-1 text-sm font-semibold text-primary-600 dark:bg-primary-900/30 dark:text-primary-300">
                    {session.finalEvaluation.overallScore} 分
                  </span>
                )}
                {isResumable(session) && (
                  <button title="继续面试" onClick={() => onContinueInterview?.(session.sessionId)} className="rounded-lg p-2 text-slate-400 hover:bg-primary-50 hover:text-primary-500">
                    <PlayCircle className="h-5 w-5" />
                  </button>
                )}
                <button title="导出 PDF" onClick={() => void exportPdf(session.sessionId)} disabled={exporting === session.sessionId} className="rounded-lg p-2 text-slate-400 hover:bg-primary-50 hover:text-primary-500 disabled:opacity-50">
                  {exporting === session.sessionId ? <Loader2 className="h-5 w-5 animate-spin" /> : <Download className="h-5 w-5" />}
                </button>
                {session.resumeId && <button title="重新开始" onClick={() => onRestartInterview?.(session.resumeId)} className="rounded-lg px-2 py-1 text-xs text-slate-500 hover:bg-slate-100">重开</button>}
                <button title="删除" onClick={() => setPendingDelete(session)} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-500"><Trash2 className="h-5 w-5" /></button>
              </div>
            </article>
          ))}
        </div>
      )}

      <DeleteConfirmDialog
        open={pendingDelete !== null}
        item={pendingDelete ? { id: 0, sessionId: pendingDelete.sessionId } : null}
        itemType="文本面试记录"
        loading={deleting}
        onConfirm={() => void remove()}
        onCancel={() => setPendingDelete(null)}
      />
    </main>
  );
}
