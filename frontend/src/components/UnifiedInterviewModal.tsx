import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronDown, ChevronUp, FileStack, Sparkles, X } from 'lucide-react';
import {
  CUSTOM_INTERVIEW_DIRECTION,
  DIFFICULTY_OPTIONS,
  type Difficulty,
  useInterviewConfig,
} from '../hooks/useInterviewConfig';
import type { CategoryDTO } from '../types/interview-config';

export type { Difficulty };

export interface UnifiedInterviewConfig {
  interviewDirection?: string;
  difficulty: Difficulty;
  resumeId: string;
  plannedDuration: number;
  targetRole: string;
  jdText?: string;
  customCategories: CategoryDTO[];
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onStart: (config: UnifiedInterviewConfig) => void;
  defaultResumeId?: string;
  title?: string;
  subtitle?: string;
  startButtonText?: string;
}

const DIRECTIONS = [
  ['java-backend', 'Java 后端'],
  ['python-backend', 'Python 后端'],
  ['frontend', '前端开发'],
  ['system-design', '系统设计'],
  ['algorithm', '算法与数据结构'],
  ['ai-agent', 'AI Agent'],
] as const;

export default function UnifiedInterviewModal({
  isOpen,
  onClose,
  onStart,
  defaultResumeId,
  title = '开始模拟面试',
  subtitle = '选择业务方向；Python Agent 会在服务端自主规划面试与 Skills',
  startButtonText = '开始面试',
}: Props) {
  const config = useInterviewConfig({ defaultResumeId, autoLoad: false });

  useEffect(() => {
    if (!isOpen) return;
    if (defaultResumeId) {
      config.setResumeId(defaultResumeId);
      config.setShowMore(true);
    }
    void config.loadResumes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, defaultResumeId]);

  const canStart = Boolean(
    config.resumeId
      && config.targetRole.trim()
      && config.plannedDuration >= 15
      && !config.isCustomStartDisabled,
  );

  const start = () => {
    if (!canStart || !config.resumeId) return;
    onStart({
      interviewDirection: config.interviewDirection,
      difficulty: config.difficulty,
      resumeId: config.resumeId,
      plannedDuration: config.plannedDuration,
      targetRole: config.targetRole.trim(),
      jdText: config.isCustomDirection ? config.customJdText.trim() : undefined,
      customCategories: [],
    });
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/50 p-4">
          <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-xl dark:bg-slate-800">
            <header className="flex items-start justify-between border-b border-slate-100 p-6 dark:border-slate-700">
              <div>
                <h2 className="text-xl font-bold text-slate-900 dark:text-white">{title}</h2>
                <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
              </div>
              <button type="button" onClick={onClose} aria-label="关闭" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100">
                <X className="h-5 w-5" />
              </button>
            </header>
            <div className="space-y-6 p-6">
              <section>
                <p className="mb-3 text-sm font-semibold">面试方向</p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {DIRECTIONS.map(([value, label]) => (
                    <button type="button" key={value} onClick={() => config.setInterviewDirection(value)} className={'rounded-xl border-2 p-3 text-left text-sm ' + (config.interviewDirection === value ? 'border-primary-500 bg-primary-50' : 'border-slate-200')}>
                      <Sparkles className="mr-2 inline h-4 w-4" />{label}
                    </button>
                  ))}
                  <button type="button" onClick={() => config.setInterviewDirection(CUSTOM_INTERVIEW_DIRECTION)} className={'rounded-xl border-2 border-dashed p-3 text-left text-sm ' + (config.isCustomDirection ? 'border-primary-500 bg-primary-50' : 'border-slate-200')}>
                    自定义 JD
                  </button>
                </div>
              </section>
              {config.isCustomDirection && (
                <textarea rows={4} value={config.customJdText} onChange={event => config.setCustomJdText(event.target.value)} placeholder="粘贴岗位描述（至少 50 个字符）" className="w-full rounded-xl border border-slate-200 p-3 text-sm" />
              )}
              <section className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-semibold">目标岗位
                  <input value={config.targetRole} onChange={event => config.setTargetRole(event.target.value)} className="mt-2 w-full rounded-xl border border-slate-200 p-3 font-normal" />
                </label>
                <label className="text-sm font-semibold">简历
                  <select value={config.resumeId ?? ''} onChange={event => config.setResumeId(event.target.value || undefined)} className="mt-2 w-full rounded-xl border border-slate-200 p-3 font-normal">
                    <option value="">请选择当前简历</option>
                    {config.resumes.map(resume => <option key={resume.id} value={resume.id}>{resume.filename ?? resume.id}</option>)}
                  </select>
                </label>
              </section>
              <section>
                <p className="mb-3 text-sm font-semibold">难度</p>
                <div className="grid grid-cols-3 gap-2">
                  {DIFFICULTY_OPTIONS.map(option => (
                    <button type="button" key={option.value} onClick={() => config.setDifficulty(option.value)} className={'rounded-xl border-2 p-3 ' + (config.difficulty === option.value ? 'border-primary-500 bg-primary-50' : 'border-slate-200')}>
                      <span className="block text-sm font-medium">{option.label}</span>
                      <span className="text-xs text-slate-400">{option.desc}</span>
                    </button>
                  ))}
                </div>
              </section>
              <button type="button" onClick={() => config.setShowMore(!config.showMore)} className="flex w-full items-center gap-2 text-sm text-slate-500">
                更多参数 {config.showMore ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
              {config.showMore && (
                <label className="block text-sm">面试时长（分钟）
                  <input type="number" min={15} max={120} value={config.plannedDuration} onChange={event => config.setPlannedDuration(Number(event.target.value))} className="mt-2 w-full rounded-lg border border-slate-200 p-2" />
                </label>
              )}
              <p className="flex items-center gap-2 text-xs text-slate-500"><FileStack className="h-4 w-4" />题目由 Python Agent 动态决定，最多 20 题。</p>
            </div>
            <footer className="flex gap-3 border-t border-slate-100 bg-slate-50 p-6">
              <button type="button" onClick={onClose} className="flex-1 rounded-xl border border-slate-200 px-4 py-3">取消</button>
              <button type="button" onClick={start} disabled={!canStart} className="flex-1 rounded-xl bg-primary-500 px-4 py-3 font-semibold text-white disabled:opacity-50">{startButtonText}</button>
            </footer>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
