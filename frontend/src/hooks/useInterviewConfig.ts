import { useEffect, useState } from 'react';
import { historyApi, type ResumeListItem } from '../api/history';
import type { CategoryDTO } from '../types/interview-config';

export type Difficulty = 'junior' | 'mid' | 'senior';
export const DIFFICULTY_OPTIONS: Array<{ value: Difficulty; label: string; desc: string }> = [
  { value: 'junior', label: '校招', desc: '基础优先' },
  { value: 'mid', label: '中级', desc: '基础与场景平衡' },
  { value: 'senior', label: '高级', desc: '场景与项目优先' },
];
export const CUSTOM_INTERVIEW_DIRECTION = 'custom';

/** The browser submits business inputs only; Python owns internal Skill selection. */
export function useInterviewConfig(options?: { defaultResumeId?: string; autoLoad?: boolean }) {
  const { defaultResumeId, autoLoad = true } = options ?? {};
  const [interviewDirection, setInterviewDirection] = useState<string | undefined>();
  const [difficulty, setDifficulty] = useState<Difficulty>('mid');
  const [showMore, setShowMore] = useState(false);
  const [resumeId, setResumeId] = useState<string | undefined>(defaultResumeId);
  const [resumes, setResumes] = useState<ResumeListItem[]>([]);
  const [plannedDuration, setPlannedDuration] = useState(30);
  const [targetRole, setTargetRole] = useState('');
  const [customJdText, setCustomJdText] = useState('');
  const [customCategories] = useState<CategoryDTO[]>([]);
  const isCustomDirection = interviewDirection === CUSTOM_INTERVIEW_DIRECTION;
  const isCustomStartDisabled = isCustomDirection && customJdText.trim().length < 50;
  const loadResumes = async () => { const data = await historyApi.getResumes(); setResumes(data); return data; };
  useEffect(() => {
    if (!autoLoad) return;
    if (defaultResumeId) { setResumeId(defaultResumeId); setShowMore(true); }
    void loadResumes();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, defaultResumeId]);
  return { interviewDirection, setInterviewDirection, difficulty, setDifficulty, showMore, setShowMore, resumeId, setResumeId, resumes, plannedDuration, setPlannedDuration, targetRole, setTargetRole, customJdText, setCustomJdText, customCategories, isCustomDirection, isCustomStartDisabled, loadResumes };
}
