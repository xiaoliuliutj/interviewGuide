import { motion } from 'framer-motion';
import { Clock, MessageSquare } from 'lucide-react';
import type { InterviewDetail } from '../api/history';
import { formatDateTime } from '../utils/date';

export default function InterviewDetailPanel({ interview }: { interview: InterviewDetail }) {
  const { session, turns } = interview;
  const report = session.finalEvaluation;

  return (
    <div className="space-y-6">
      <section className="rounded-2xl bg-gradient-to-r from-primary-500 to-indigo-600 p-6 text-white">
        <h2 className="text-xl font-bold">文本面试记录</h2>
        <div className="mt-4 grid gap-3 text-sm text-white/90 sm:grid-cols-4">
          <span>状态：{session.status}</span>
          <span>难度：{session.difficulty}</span>
          <span>当前阶段主问题：{session.primaryQuestionCount}</span>
          <span>累计主问题：{session.totalPrimaryQuestionCount}</span>
          <span>已发出问题：{session.issuedQuestionCount}</span>
        </div>
        <p className="mt-4 text-sm text-white/80">当前阶段：{session.currentStage ?? 'SUMMARY'}，当前问题追问：{session.followupCount} 次，动态安全上限：{session.totalQuestions} 题。</p>
      </section>

      {report && Object.keys(report).length > 0 && (
        <section className="rounded-2xl bg-white p-6 shadow-sm dark:bg-slate-800">
          <h3 className="font-semibold text-slate-800 dark:text-white">最终评估</h3>
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            综合评分：{report.overallScore ?? '-'} 分。{report.summary ?? ''}
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-3 text-sm">
            <div><h4 className="font-medium text-emerald-600">表现较好</h4><p className="mt-1 text-slate-600 dark:text-slate-300">{report.strengths?.join('；') || '暂无'}</p></div>
            <div><h4 className="font-medium text-amber-600">需要提升</h4><p className="mt-1 text-slate-600 dark:text-slate-300">{report.weaknesses?.join('；') || '暂无'}</p></div>
            <div><h4 className="font-medium text-primary-600">改进建议</h4><p className="mt-1 text-slate-600 dark:text-slate-300">{report.suggestions?.join('；') || '暂无'}</p></div>
          </div>
        </section>
      )}

      <section>
        <h3 className="mb-4 flex items-center gap-2 font-semibold text-slate-800 dark:text-white">
          <MessageSquare className="h-5 w-5 text-primary-500" />问答记录
        </h3>
        {turns.length === 0 ? (
          <p className="rounded-xl bg-slate-50 p-5 text-sm text-slate-500 dark:bg-slate-800">当前还没有已提交的回答。</p>
        ) : (
          <div className="space-y-4">
            {turns.map((turn, index) => (
              <motion.article key={`${turn.index}-${turn.question}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .04 }} className="rounded-2xl bg-white p-5 shadow-sm dark:bg-slate-800">
                <div className="flex items-center justify-between gap-3">
                  <span className="rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary-600 dark:bg-primary-900/30">{turn.stage}</span>
                  {turn.answeredAt && <span className="flex items-center gap-1 text-xs text-slate-400"><Clock className="h-3.5 w-3.5" />{formatDateTime(turn.answeredAt)}</span>}
                </div>
                <h4 className="mt-4 font-medium leading-relaxed text-slate-800 dark:text-white">{turn.index + 1}. {turn.question}</h4>
                <div className="mt-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-900/40">
                  <p className="mb-1 text-xs text-slate-500">你的回答</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 dark:text-slate-300">{turn.answer ?? '未回答'}</p>
                  {turn.evaluationSummary && <p className="mt-3 rounded-lg bg-primary-50 p-3 text-sm text-primary-700 dark:bg-primary-900/20 dark:text-primary-300">回答评估：{turn.evaluationSummary}{turn.score == null ? '' : `（${turn.score} 分）`}</p>}
                </div>
              </motion.article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
