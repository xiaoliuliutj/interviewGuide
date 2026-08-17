import { useState } from 'react';
import { Calendar, Download, MessageSquare, Trash2 } from 'lucide-react';
import type { InterviewItem } from '../api/history';
import { historyApi } from '../api/history';
import ConfirmDialog from './ConfirmDialog';
import { formatDateOnly } from '../utils/date';

interface Props {
  interviews: InterviewItem[];
  onStartInterview: () => void;
  onViewInterview: (sessionId: string) => void;
  onExportInterview: (sessionId: string) => void;
  onDeleteInterview: (sessionId: string) => void;
  exporting: string | null;
  loadingInterview: boolean;
}

export default function InterviewPanel({ interviews, onStartInterview, onViewInterview, onExportInterview, onDeleteInterview, exporting, loadingInterview }: Props) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try { await historyApi.deleteInterview(pendingDelete); onDeleteInterview(pendingDelete); setPendingDelete(null); } finally { setDeleting(false); }
  };
  if (interviews.length === 0) return <div className="rounded-2xl bg-white p-10 text-center shadow-sm dark:bg-slate-800"><MessageSquare className="mx-auto h-10 w-10 text-slate-400" /><h3 className="mt-3 font-semibold text-slate-800 dark:text-white">暂无文本面试记录</h3><button onClick={onStartInterview} className="mt-5 rounded-xl bg-primary-500 px-5 py-2.5 text-sm font-semibold text-white">开始面试</button></div>;
  return <section className="space-y-4">{interviews.map((interview, index) => <article key={interview.sessionId} onClick={() => onViewInterview(interview.sessionId)} className="flex cursor-pointer items-center gap-4 rounded-2xl bg-white p-5 shadow-sm transition hover:bg-slate-50 dark:bg-slate-800 dark:hover:bg-slate-700/50"><div className="rounded-xl bg-primary-50 p-3 text-primary-500 dark:bg-primary-900/30"><MessageSquare className="h-5 w-5" /></div><div className="min-w-0 flex-1"><h3 className="font-medium text-slate-800 dark:text-white">文本面试 #{interviews.length - index}</h3><p className="mt-1 flex items-center gap-2 text-sm text-slate-500"><Calendar className="h-4 w-4" />{formatDateOnly(interview.createdAt)} · 已发出 {interview.issuedQuestionCount} 题 · 动态上限 {interview.totalQuestions} · {interview.status}</p>{interview.finalEvaluation?.summary && <p className="mt-2 line-clamp-2 text-xs text-slate-500">面试评价：{interview.finalEvaluation.summary}</p>}</div>{interview.finalEvaluation?.overallScore != null && <span className="rounded-full bg-primary-50 px-3 py-1 text-sm font-semibold text-primary-600 dark:bg-primary-900/30 dark:text-primary-300">{interview.finalEvaluation.overallScore} 分</span>}<div className="flex gap-1"><button onClick={event => { event.stopPropagation(); onExportInterview(interview.sessionId); }} disabled={exporting === interview.sessionId} title="导出 PDF" className="rounded-lg p-2 text-slate-400 hover:bg-primary-50 hover:text-primary-500 disabled:opacity-50"><Download className="h-5 w-5" /></button><button onClick={event => { event.stopPropagation(); setPendingDelete(interview.sessionId); }} title="删除记录" className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-500"><Trash2 className="h-5 w-5" /></button></div></article>)}{loadingInterview && <p className="text-sm text-slate-500">正在加载面试详情…</p>}<ConfirmDialog open={pendingDelete !== null} title="删除面试记录" message="确定删除这条面试记录吗？此操作不可恢复。" confirmText="删除" cancelText="取消" confirmVariant="danger" loading={deleting} onConfirm={() => void confirmDelete()} onCancel={() => setPendingDelete(null)} /></section>;
}
