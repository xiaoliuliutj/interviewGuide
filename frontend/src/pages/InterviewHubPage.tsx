import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FileStack, Loader2, Sparkles } from 'lucide-react';
import { interviewApi, type TextSessionMeta } from '../api/interview';
import { formatDateTime } from '../utils/date';
import {
  CUSTOM_INTERVIEW_DIRECTION,
  DIFFICULTY_OPTIONS,
  useInterviewConfig,
} from '../hooks/useInterviewConfig';

const DIRECTIONS = [
  ['java-backend', 'Java 后端'],
  ['python-backend', 'Python 后端'],
  ['frontend', '前端开发'],
  ['system-design', '系统设计'],
  ['algorithm', '算法与数据结构'],
  ['ai-agent', 'AI Agent'],
] as const;

const isResumable = (session: TextSessionMeta) =>
  session.status === 'ACTIVE' || session.status === 'PAUSED';

export default function InterviewHubPage() {
  const navigate = useNavigate();
  const config = useInterviewConfig();
  const [recentSessions, setRecentSessions] = useState<TextSessionMeta[]>([]);
  const [unfinishedSession, setUnfinishedSession] = useState<TextSessionMeta | null>(null);
  const [loadingRecent, setLoadingRecent] = useState(true);
  const [error, setError] = useState('');

  const loadRecent = useCallback(async () => {
    setLoadingRecent(true);
    try {
      const [sessions, unfinished] = await Promise.all([
        interviewApi.listSessions(),
        interviewApi.findUnfinishedSession(),
      ]);
      setRecentSessions(sessions.slice(0, 5));
      setUnfinishedSession(unfinished);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '加载面试记录失败');
    } finally {
      setLoadingRecent(false);
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  const canStart = Boolean(
    config.resumeId
      && config.targetRole.trim()
      && config.plannedDuration >= 15
      && !config.isCustomStartDisabled,
  );

  const startInterview = () => {
    if (unfinishedSession) {
      if (unfinishedSession.status === 'CREATING') {
        setError('当前面试正在创建中，请稍候刷新页面后继续。');
        return;
      }
      navigate('/interview', { state: { sessionIdToResume: unfinishedSession.sessionId } });
      return;
    }
    if (!canStart || !config.resumeId) return;
    navigate('/interview', {
      state: {
        resumeId: config.resumeId,
        interviewConfig: {
          interviewDirection: config.interviewDirection,
          difficulty: config.difficulty,
          targetRole: config.targetRole.trim(),
          interviewDurationMinutes: config.plannedDuration,
          jdText: config.isCustomDirection ? config.customJdText.trim() : undefined,
          customCategories: [],
        },
      },
    });
  };

  return (
    <main className="mx-auto max-w-5xl space-y-8">
      <header>
        <h1 className="flex items-center gap-3 text-2xl font-bold text-slate-800 dark:text-white">
          <Sparkles className="h-7 w-7 text-primary-500" />文本模拟面试
        </h1>
        <p className="mt-1 text-slate-500 dark:text-slate-400">
          前端只提交业务参数；Java 负责业务编排，Python Agent 在服务端自主选择 Skills 并规划面试。
        </p>
      </header>
      <section className="space-y-6 rounded-2xl border border-slate-100 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm font-semibold text-slate-700 dark:text-slate-200">目标岗位
            <input value={config.targetRole} onChange={event => config.setTargetRole(event.target.value)} placeholder="例如：Java 后端实习生" className="mt-2 w-full rounded-xl border border-slate-200 p-3 font-normal dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
          </label>
          <label className="text-sm font-semibold text-slate-700 dark:text-slate-200">当前简历
            <select value={config.resumeId ?? ''} onChange={event => config.setResumeId(event.target.value || undefined)} className="mt-2 w-full rounded-xl border border-slate-200 p-3 font-normal dark:border-slate-700 dark:bg-slate-900 dark:text-white">
              <option value="">请选择当前简历</option>
              {config.resumes.map(resume => <option key={resume.id} value={resume.id}>{resume.filename ?? resume.id}</option>)}
            </select>
          </label>
        </div>
        <div>
          <p className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">面试方向</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {DIRECTIONS.map(([value, label]) => (
              <button type="button" key={value} onClick={() => config.setInterviewDirection(value)} className={'rounded-xl border-2 p-3 text-left text-sm ' + (config.interviewDirection === value ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-slate-200 dark:border-slate-700')}>
                {label}
              </button>
            ))}
            <button type="button" onClick={() => config.setInterviewDirection(CUSTOM_INTERVIEW_DIRECTION)} className={'rounded-xl border-2 border-dashed p-3 text-left text-sm ' + (config.isCustomDirection ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-slate-200 dark:border-slate-700')}>
              自定义 JD
            </button>
          </div>
        </div>
        {config.isCustomDirection && (
          <textarea rows={4} value={config.customJdText} onChange={event => config.setCustomJdText(event.target.value)} placeholder="粘贴岗位描述（至少 50 个字符）" className="w-full rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-white" />
        )}
        <div>
          <p className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">难度</p>
          <div className="grid grid-cols-3 gap-2">
            {DIFFICULTY_OPTIONS.map(option => (
              <button type="button" key={option.value} onClick={() => config.setDifficulty(option.value)} className={'rounded-xl border-2 p-3 text-center ' + (config.difficulty === option.value ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20' : 'border-slate-200 dark:border-slate-700')}>
                <span className="block text-sm font-medium">{option.label}</span>
                <span className="text-xs text-slate-400">{option.desc}</span>
              </button>
            ))}
          </div>
        </div>
        <label className="text-sm text-slate-600 dark:text-slate-300">面试时长（分钟）
          <input type="number" min={15} max={120} value={config.plannedDuration} onChange={event => config.setPlannedDuration(Number(event.target.value))} className="mt-2 w-full rounded-lg border border-slate-200 p-2 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
        </label>
        {error && <p className="text-sm text-red-500">{error}</p>}
        {unfinishedSession && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
            {unfinishedSession.status === 'CREATING'
              ? '当前面试正在创建中，请等待创建请求结束后再继续。'
              : '当前存在未完成面试。刷新页面或再次点击开始都不会创建新会话，请先继续、正常结束或关闭当前面试。'}
          </div>
        )}
        <button type="button" onClick={startInterview} disabled={unfinishedSession?.status === 'CREATING' || (!canStart && !unfinishedSession)} className="rounded-xl bg-primary-500 px-6 py-3 font-semibold text-white disabled:opacity-50">
          {unfinishedSession?.status === 'CREATING' ? '面试创建中' : unfinishedSession ? '继续当前面试' : '开始文本面试'}
        </button>
      </section>
      <section className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm dark:border-slate-700 dark:bg-slate-800">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-slate-800 dark:text-white">最近文本面试</h2>
          <Link to="/interviews" className="text-sm text-primary-500">查看全部</Link>
        </div>
        {loadingRecent ? <Loader2 className="h-5 w-5 animate-spin text-primary-500" /> : recentSessions.length === 0 ? <p className="text-sm text-slate-500">暂无记录。</p> : (
          <div className="space-y-3">
            {recentSessions.map(session => {
              const resumable = isResumable(session);
              return (
                <button type="button" key={session.sessionId} onClick={() => navigate(resumable ? '/interview' : '/interviews/' + session.sessionId, { state: resumable ? { sessionIdToResume: session.sessionId } : undefined })} className="flex w-full items-center justify-between rounded-xl bg-slate-50 p-4 text-left hover:bg-slate-100 dark:bg-slate-900/40">
                  <span className="flex items-center gap-3">
                    <FileStack className="h-5 w-5 text-primary-500" />
                    <span>
                      <span className="block font-medium text-slate-800 dark:text-white">{session.interviewDirection ?? '通用面试'}</span>
                      <span className="text-xs text-slate-500">{formatDateTime(session.createdAt)}</span>
                    </span>
                  </span>
                  <span className="text-sm text-slate-500">{resumable ? '继续' : '查看'}</span>
                </button>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
