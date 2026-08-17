import {useEffect, useRef, useState} from 'react';
import {motion} from 'framer-motion';
import {interviewApi} from '../api/interview';
import ConfirmDialog from '../components/ConfirmDialog';
import InterviewChatPanel from '../components/InterviewChatPanel';
import InterviewMessageBubble from '../components/InterviewMessageBubble';
import InterviewPageHeader from '../components/InterviewPageHeader';
import type {InterviewQuestion, InterviewSession} from '../types/interview';
import type {Difficulty} from '../components/UnifiedInterviewModal';
import type {CategoryDTO} from '../types/interview-config';
import {historyApi} from '../api/history';
import {ApiRequestError, createClientId, getErrorDisplayMessage} from '../api/request';

interface Message {
  type: 'interviewer' | 'user';
  content: string;
  category?: string;
  questionIndex?: number;
  submissionRunId?: string;
}

interface PendingAnswerSubmission {
  sessionId: string;
  question: string;
  answer: string;
  runId: string;
}

function pendingAnswerStorageKey(sessionId: string): string {
  return `interview.pending-answer.${sessionId}`;
}

function loadPendingAnswerSubmission(sessionId: string): PendingAnswerSubmission | null {
  try {
    const raw = sessionStorage.getItem(pendingAnswerStorageKey(sessionId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PendingAnswerSubmission>;
    if (value.sessionId !== sessionId
      || typeof value.question !== 'string'
      || typeof value.answer !== 'string'
      || typeof value.runId !== 'string') return null;
    return value as PendingAnswerSubmission;
  } catch {
    return null;
  }
}

interface InterviewProps {
  resumeText: string;
  resumeId?: string;
  sessionIdToResume?: string;
  initialConfig?: {
    interviewDirection?: string;
    difficulty?: Difficulty;
    customCategories?: CategoryDTO[];
    jdText?: string;
    targetRole?: string;
    interviewDurationMinutes?: number;
  };
  onBack: () => void;
}

export default function Interview({
  resumeText: _resumeText,
  resumeId,
  sessionIdToResume,
  initialConfig,
  onBack,
}: InterviewProps) {
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<InterviewQuestion | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [agentStatus, setAgentStatus] = useState('IDLE');
  const [error, setError] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [showCompleteConfirm, setShowCompleteConfirm] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [blockedSession, setBlockedSession] = useState<InterviewSession | null>(null);
  const startedRef = useRef(false);
  const pendingAnswerSubmissionRef = useRef<PendingAnswerSubmission | null>(null);

  const interviewDirection = initialConfig?.interviewDirection;
  const difficulty = initialConfig?.difficulty;
  const customCategories = initialConfig?.customCategories ?? [];
  const jdText = initialConfig?.jdText;
  const targetRole = initialConfig?.targetRole;
  const interviewDurationMinutes = initialConfig?.interviewDurationMinutes;

  useEffect(() => {
    if (!isSubmitting || !session) return;
    let active = true;
    const poll = async () => {
      try {
        const stage = await interviewApi.getAgentStatus(session.sessionId);
        // The progress request can race ahead of the answer request and see
        // the previous IDLE state. Never let that stale observation overwrite
        // the active phase already shown after the user clicked submit.
        if (active && stage !== 'IDLE') setAgentStatus(stage);
      } catch {
        if (active) setAgentStatus('STATUS_UNAVAILABLE');
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [isSubmitting, session?.sessionId]);

  // 自动开始面试（恢复已有会话 或 创建新会话）
  useEffect(() => {
    if (!startedRef.current) {
      startedRef.current = true;
      void initializeInterview();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const initializeInterview = async () => {
    try {
      if (sessionIdToResume) {
        await resumeExistingSession(sessionIdToResume);
        return;
      }
      const unfinished = await interviewApi.findUnfinishedSession();
      if (unfinished) {
        setBlockedSession(unfinished);
        return;
      }
      await startInterview();
    } catch (err) {
      setError(getErrorDisplayMessage(err, '检查未完成面试失败'));
    }
  };

  const startInterview = async () => {
    setIsCreating(true);
    setError('');

    try {
      const unfinished = await interviewApi.findUnfinishedSession();
      if (unfinished) {
        setBlockedSession(unfinished);
        return;
      }
      if (!resumeId || !difficulty || !targetRole || !interviewDurationMinutes) {
        throw new Error('缺少创建面试所需的简历、岗位、难度或时长参数');
      }
      const newSession = await interviewApi.createSession({
        resumeId,
        targetRole,
        interviewDurationMinutes,
        interviewDirection,
        difficulty,
        jdText,
        customCategories,
      });

      initSession(newSession);
    } catch (err) {
      setError(getErrorDisplayMessage(err, '创建面试失败'));
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const resumeExistingSession = async (sessionId: string) => {
    setIsCreating(true);
    setError('');

    try {
      const existingSession = await interviewApi.getSession(sessionId);
      initSession(existingSession);

      // 恢复已填写的答案
      const currentQ = existingSession.questions[existingSession.currentQuestionIndex];
      if (currentQ?.userAnswer) {
        setAnswer(currentQ.userAnswer);
      }
    } catch (err) {
      setError(getErrorDisplayMessage(err, '恢复面试失败'));
      console.error(err);
    } finally {
      setIsCreating(false);
    }
  };

  const initSession = (s: InterviewSession, rebuildMessages = true) => {
    setSession(s);

    if (s.questions.length > 0) {
      const activeQuestions = s.status === 'ACTIVE' || s.status === 'PAUSED'
        ? s.questions.filter(question => question.userAnswer === null)
        : [];
      const currentQ = activeQuestions.length > 0 ? activeQuestions[activeQuestions.length - 1] : null;
      const idx = currentQ ? s.questions.findIndex(question => question.questionIndex === currentQ.questionIndex) : -1;
      setCurrentQuestion(currentQ);
      const pending = loadPendingAnswerSubmission(s.sessionId);
      if (pending && currentQ && pending.question === currentQ.question && currentQ.userAnswer === null) {
        pendingAnswerSubmissionRef.current = pending;
        setAnswer(pending.answer);
      }

      if (!rebuildMessages) return;

      // 重建消息历史
      const restoredMessages: Message[] = [];
      for (let i = 0; i < s.questions.length; i++) {
        const q = s.questions[i];
        restoredMessages.push({
          type: 'interviewer',
          content: q.question,
          // 历史消息不重复展示阶段标签，页面只突出当前阶段。
          category: i === idx ? q.category : undefined,
          questionIndex: i
        });
        if (q.userAnswer) {
          restoredMessages.push({
            type: 'user',
            content: q.userAnswer
          });
          if (q.evaluationSummary) {
            restoredMessages.push({
              type: 'interviewer',
              content: `回答评估：${q.evaluationSummary}${q.score == null ? '' : `（${q.score} 分）`}`,
              category: q.category,
            });
          }
        }
      }
      if (s.status === 'COMPLETED') {
        restoredMessages.push({
          type: 'interviewer',
          content: '本次面试已结束，下面是本次面试的综合评估。',
          category: 'SUMMARY',
        });
      }
      setMessages(restoredMessages);
    } else {
      setCurrentQuestion(null);
      if (rebuildMessages) setMessages([]);
    }
  };

  const handleSubmitAnswer = async () => {
    if (!answer.trim() || !session || !currentQuestion) return;

    try {
      setIsSubmitting(true);
      setAgentStatus('EVALUATING');
      setError('');
      const submittedAnswer = answer.trim();
      const previous = pendingAnswerSubmissionRef.current;
      const isRetry = previous !== null
        && previous.sessionId === session.sessionId
        && previous.question === currentQuestion.question
        && previous.answer === submittedAnswer;
      const submission: PendingAnswerSubmission = isRetry && previous
        ? previous
        : {
            sessionId: session.sessionId,
            question: currentQuestion.question,
            answer: submittedAnswer,
            runId: createClientId('answer-run'),
          };
      pendingAnswerSubmissionRef.current = submission;
      sessionStorage.setItem(pendingAnswerStorageKey(session.sessionId), JSON.stringify(submission));

      if (!isRetry) {
        const userMessage: Message = {
          type: 'user', content: submittedAnswer, submissionRunId: submission.runId,
        };
        setMessages(prev => [
          ...prev.filter(message => message.submissionRunId !== previous?.runId),
          userMessage,
        ]);
      }

      const response = await interviewApi.submitAnswer({
        sessionId: session.sessionId,
        answer: submittedAnswer,
        runId: submission.runId,
      });

      pendingAnswerSubmissionRef.current = null;
      sessionStorage.removeItem(pendingAnswerStorageKey(session.sessionId));
      setAnswer('');

      // 每轮都使用后端返回的完整问答记录重建消息。这样无论正常提交、
      // 网络重试还是幂等重放，旧问题、用户回答、逐轮评估和下一题都不会丢失。
      initSession(response.session);
    } catch (err) {
      if (err instanceof ApiRequestError && err.code === '303') {
        onBack();
        return;
      }
      setError(getErrorDisplayMessage(err, '提交答案失败'));
      console.error(err);
    } finally {
      setIsSubmitting(false);
      setAgentStatus('IDLE');
    }
  };

  const handleCompleteEarly = async () => {
    if (!session) return;

    setIsSubmitting(true);
    setAgentStatus('SUMMARIZING');
    try {
      await interviewApi.completeInterview(session.sessionId);
      setShowCompleteConfirm(false);
      const completed = await interviewApi.getSession(session.sessionId);
      initSession(completed);
    } catch (err) {
      if (err instanceof ApiRequestError && err.code === '303') {
        onBack();
        return;
      }
      setError(getErrorDisplayMessage(err, '提前交卷失败'));
      console.error(err);
    } finally {
      setIsSubmitting(false);
      setAgentStatus('IDLE');
    }
  };

  const handleCloseInterview = async () => {
    if (!session) return;
    setIsSubmitting(true);
    setAgentStatus('CLOSING');
    try {
      await interviewApi.closeInterview(session.sessionId);
      sessionStorage.removeItem(pendingAnswerStorageKey(session.sessionId));
      setShowCloseConfirm(false);
      onBack();
    } catch (err) {
      setError(getErrorDisplayMessage(err, '关闭面试失败'));
      console.error(err);
    } finally {
      setIsSubmitting(false);
      setAgentStatus('IDLE');
    }
  };

  // 加载中
  if (isCreating) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-center">
          <div className="w-10 h-10 border-3 border-slate-200 border-t-primary-500 rounded-full mx-auto mb-4 animate-spin" />
          <p className="text-slate-500 dark:text-slate-400">正在生成面试题目...</p>
        </div>
      </div>
    );
  }

  // 错误状态
  if (error && !session) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <div className="text-center">
          <p className="text-red-500 dark:text-red-400 mb-4">{error}</p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={startInterview}
              className="px-5 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600"
            >
              重试
            </button>
            <button
              onClick={onBack}
              className="px-5 py-2 bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-300 dark:hover:bg-slate-600"
            >
              返回
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (blockedSession && !session) {
    const isCreatingSession = blockedSession.status === 'CREATING';
    return (
      <div className="mx-auto max-w-xl rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center dark:border-amber-800 dark:bg-amber-900/20">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white">已有未完成的面试</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
          {isCreatingSession
            ? '当前面试正在创建中。创建完成后刷新页面即可继续，期间不会创建新的面试。'
            : '刷新页面不会创建新的面试。请继续当前面试，或关闭它后再开始新的面试。'}
        </p>
        <div className="mt-5 flex justify-center gap-3">
          {!isCreatingSession && (
            <button
              type="button"
              onClick={() => void resumeExistingSession(blockedSession.sessionId)}
              className="rounded-xl bg-primary-500 px-5 py-2.5 font-semibold text-white"
            >
              继续当前面试
            </button>
          )}
          <button
            type="button"
            onClick={onBack}
            className="rounded-xl border border-slate-300 px-5 py-2.5 text-slate-700 dark:border-slate-600 dark:text-slate-200"
          >
            返回
          </button>
        </div>
      </div>
    );
  }

  if (!session) return null;

  const downloadReport = async () => {
    try {
      const blob = await historyApi.exportInterviewPdf(session.sessionId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `interview-${session.sessionId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getErrorDisplayMessage(err, '评估报告下载失败'));
      console.error(err);
    }
  };

  if (session.status === 'COMPLETED') {
    const report = session.finalEvaluation;
    return (
      <div className="mx-auto max-w-4xl space-y-5 pb-10">
        <InterviewPageHeader title="面试完成" subtitle="以下是本次面试的综合评估" icon={<span className="text-xl">✓</span>} />
        <section className="rounded-2xl bg-white p-6 shadow-sm dark:bg-slate-800">
          <h2 className="mb-4 text-lg font-semibold text-slate-800 dark:text-white">面试对话记录</h2>
          <div className="max-h-[32rem] space-y-3 overflow-y-auto rounded-xl bg-slate-50 p-4 dark:bg-slate-900/40">
            {messages.map((message, index) => (
              <InterviewMessageBubble key={`${index}-${message.content}`} role={message.type === 'interviewer' ? 'interviewer' : 'user'} text={message.content} category={message.category} />
            ))}
          </div>
        </section>
        <section className="rounded-2xl bg-white p-6 shadow-sm dark:bg-slate-800">
          <div className="flex items-center justify-between gap-3"><h2 className="text-xl font-semibold text-slate-800 dark:text-white">最终评估</h2><button onClick={() => void downloadReport()} className="rounded-lg bg-primary-500 px-4 py-2 text-sm font-semibold text-white">下载评估 PDF</button></div>
          <p className="mt-4 text-slate-700 dark:text-slate-300">综合评分：{report.overallScore ?? '-'} 分</p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-600 dark:text-slate-300">{report.summary ?? '本次面试已完成。'}</p>
          <div className="mt-5 grid gap-4 md:grid-cols-3"><div><h3 className="font-medium text-emerald-600">表现较好</h3><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{report.strengths?.join('；') || '暂无'}</p></div><div><h3 className="font-medium text-amber-600">需要提升</h3><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{report.weaknesses?.join('；') || '暂无'}</p></div><div><h3 className="font-medium text-primary-600">改进建议</h3><p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{report.suggestions?.join('；') || '暂无'}</p></div></div>
        </section>
      </div>
    );
  }

  if (!currentQuestion) return null;

  return (
    <div className="pb-10">
      <InterviewPageHeader
        title="模拟面试"
        subtitle="认真回答每个问题，展示您的实力"
        icon={(
          <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="none">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <line x1="12" y1="19" x2="12" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <line x1="8" y1="23" x2="16" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )}
      />

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        {error && (
          <div className="mx-auto mb-4 max-w-4xl rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300" role="alert">
            {error}。你的回答已保留，可直接再次提交；系统会复用同一个请求编号，避免重复记录。
          </div>
        )}
        <InterviewChatPanel
          session={session}
          currentQuestion={currentQuestion}
          messages={messages}
          answer={answer}
          onAnswerChange={setAnswer}
          onSubmit={handleSubmitAnswer}
          isSubmitting={isSubmitting}
          agentStatus={agentStatus}
          onShowCompleteConfirm={setShowCompleteConfirm}
          onShowCloseConfirm={setShowCloseConfirm}
        />
      </motion.div>

      {/* 提前交卷确认对话框 */}
      <ConfirmDialog
        open={showCompleteConfirm}
        title="提前交卷"
        message="确定要提前交卷吗？未回答的问题将按0分计算。"
        confirmText="确定交卷"
        cancelText="取消"
        confirmVariant="warning"
        loading={isSubmitting}
        onConfirm={handleCompleteEarly}
        onCancel={() => setShowCompleteConfirm(false)}
      />
      <ConfirmDialog
        open={showCloseConfirm}
        title="关闭并删除面试"
        message="关闭后不会生成评估，当前面试和回答记录也不会保留。确定继续吗？"
        confirmText="关闭并删除"
        cancelText="继续面试"
        confirmVariant="danger"
        loading={isSubmitting}
        onConfirm={() => void handleCloseInterview()}
        onCancel={() => setShowCloseConfirm(false)}
      />
    </div>
  );
}
