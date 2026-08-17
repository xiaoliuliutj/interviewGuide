import { useState } from 'react';
import { knowledgeBaseApi } from '../api/knowledgebase';
import type { UploadKnowledgeBaseResponse, WebCrawlResult, WebFetchResult } from '../api/knowledgebase';
import FileUploadCard from '../components/FileUploadCard';

interface KnowledgeBaseUploadPageProps {
  onUploadComplete: (result: UploadKnowledgeBaseResponse) => void;
  onBack: () => void;
}

export default function KnowledgeBaseUploadPage({ onUploadComplete, onBack }: KnowledgeBaseUploadPageProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const [webLoading, setWebLoading] = useState(false);
  const [webPreview, setWebPreview] = useState<WebFetchResult | null>(null);
  const [crawlTopic, setCrawlTopic] = useState('');
  const [crawlPreview, setCrawlPreview] = useState<WebCrawlResult | null>(null);
  const [selectedPages, setSelectedPages] = useState<Set<string>>(new Set());

  const handleUpload = async (file: File, name?: string) => {
    setUploading(true);
    setError('');

    try {
      const data = await knowledgeBaseApi.uploadKnowledgeBase(file, name);
      onUploadComplete(data);
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : '上传失败，请重试';
      setError(errorMessage);
      setUploading(false);
    }
  };

  const handleReadWeb = async () => {
    if (!url.trim()) return;
    setWebLoading(true);
    setError('');
    setWebPreview(null);
    try {
      const preview = await knowledgeBaseApi.fetchWebPage(url.trim());
      setWebPreview(preview);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '网页读取失败');
    } finally {
      setWebLoading(false);
    }
  };

  const handleImportWeb = async () => {
    if (!webPreview) return;
    setWebLoading(true);
    setError('');
    try {
      const safeName = (webPreview.title || 'web-article').replace(/[\\/:*?"<>|]/g, '_').slice(0, 80);
      const file = new File([webPreview.markdown], `${safeName || 'web-article'}.md`, {type: 'text/markdown'});
      const data = await knowledgeBaseApi.uploadKnowledgeBase(file, webPreview.title, undefined, webPreview);
      onUploadComplete(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '网页知识库导入失败');
    } finally {
      setWebLoading(false);
    }
  };

  const handleCrawl = async () => {
    if (!url.trim()) return;
    setWebLoading(true); setError(''); setCrawlPreview(null);
    try {
      const result = await knowledgeBaseApi.crawlWebSite(url.trim(), crawlTopic.trim() || undefined);
      setCrawlPreview(result);
      setSelectedPages(new Set(result.pages.map(page => page.id)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '目录抓取失败');
    } finally { setWebLoading(false); }
  };

  const downloadMarkdown = (filename: string, content: string) => {
    const blobUrl = URL.createObjectURL(new Blob([content], {type: 'text/markdown;charset=utf-8'}));
    const link = document.createElement('a'); link.href = blobUrl; link.download = filename;
    document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(blobUrl);
  };

  const handleDownloadArchive = async () => {
    if (!crawlPreview) return;
    try {
      const archive = await knowledgeBaseApi.downloadWebCrawlArchive(crawlPreview.previewToken);
      const blobUrl = URL.createObjectURL(archive);
      const link = document.createElement('a'); link.href = blobUrl; link.download = 'web-crawl-sources.md';
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(blobUrl);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '溯源归档下载失败');
    }
  };

  const handleImportCrawl = async () => {
    if (!crawlPreview) return;
    const pages = crawlPreview.pages.filter(page => selectedPages.has(page.id));
    if (!pages.length) return;
    setWebLoading(true); setError('');
    try {
      const imported = await knowledgeBaseApi.importWebCrawl(
        crawlPreview.previewToken, pages.map(page => page.id),
      );
      const first = imported.knowledgeBases[0];
      onUploadComplete({knowledgeBase: {id: first?.id ?? 0, name: `${imported.importedCount} 个网页页面`, category: '', fileSize: 0, contentLength: pages.reduce((sum, page) => sum + page.characterCount, 0)}});
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '网页页面导入失败');
    } finally { setWebLoading(false); }
  };

  return (
    <div className="space-y-8">
      <FileUploadCard
      title="上传知识库"
      subtitle="上传文档，面试 Agent 会在生成相关题目时检索其中内容"
      accept=".pdf,.doc,.docx,.txt,.md"
      formatHint="支持 PDF、DOCX、DOC、TXT、MD"
      maxSizeHint="最大 50MB"
      uploading={uploading}
      uploadButtonText="开始上传"
      selectButtonText="选择文件"
      showNameInput={true}
      nameLabel="知识库名称（可选）"
      namePlaceholder="留空则使用文件名"
      error={error}
      onUpload={handleUpload}
      onBack={onBack}
      />
      <section className="max-w-3xl mx-auto bg-white dark:bg-slate-800 rounded-2xl p-8 shadow-lg">
        <h2 className="text-xl font-semibold text-slate-900 dark:text-white">从公开网页读取</h2>
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
          Agent 只读取你明确提供的公开 HTTP(S) 页面，并先生成 Markdown 预览；不会执行网页脚本。
        </p>
        <div className="mt-5 flex gap-3">
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Enter') void handleReadWeb(); }}
            placeholder="https://example.com/article"
            className="flex-1 px-4 py-3 border border-slate-200 dark:border-slate-600 rounded-xl bg-white dark:bg-slate-700 text-slate-900 dark:text-white"
            disabled={webLoading}
          />
          <button
            type="button"
            onClick={() => void handleReadWeb()}
            disabled={webLoading || !url.trim()}
            className="px-5 py-3 rounded-xl bg-indigo-500 text-white font-medium disabled:opacity-50"
          >
            {webLoading ? '读取中…' : '读取网页'}
          </button>
        </div>
        <div className="mt-3 flex gap-3">
          <input value={crawlTopic} onChange={event => setCrawlTopic(event.target.value)}
            placeholder="知识主题（可选，例如：Java 并发）"
            className="flex-1 px-4 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white" disabled={webLoading}/>
          <button type="button" onClick={() => void handleCrawl()} disabled={webLoading || !url.trim()}
            className="px-4 py-2 rounded-lg border border-indigo-300 text-indigo-600 dark:text-indigo-300 disabled:opacity-50">
            {webLoading ? '抓取中…' : '深入抓取目录'}
          </button>
        </div>
        {webPreview && (
          <div className="mt-6 border border-slate-200 dark:border-slate-600 rounded-xl overflow-hidden">
            <div className="p-4 bg-slate-50 dark:bg-slate-700/50">
              <h3 className="font-semibold text-slate-900 dark:text-white">{webPreview.title}</h3>
              <p className="mt-1 text-xs text-slate-500 break-all">{webPreview.url}</p>
              <p className="mt-1 text-xs text-slate-500">{webPreview.characterCount.toLocaleString()} 字符 · {new Date(webPreview.fetchedAt).toLocaleString()}</p>
            </div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap p-4 text-sm text-slate-700 dark:text-slate-200">{webPreview.markdown}</pre>
            <div className="p-4 flex items-center justify-between gap-4 border-t border-slate-200 dark:border-slate-600">
              <p className="text-xs text-amber-600 dark:text-amber-400">请确认内容和来源可信后再导入。</p>
              <button type="button" onClick={() => void handleImportWeb()} disabled={webLoading}
                className="shrink-0 px-4 py-2 rounded-lg bg-emerald-500 text-white font-medium disabled:opacity-50">
                确认并导入知识库
              </button>
            </div>
          </div>
        )}
        {crawlPreview && (
          <div className="mt-6 border border-indigo-200 dark:border-indigo-700 rounded-xl overflow-hidden">
            <div className="p-4 bg-indigo-50 dark:bg-indigo-900/20 flex items-center justify-between gap-3">
              <div><h3 className="font-semibold text-slate-900 dark:text-white">深度抓取结果：{crawlPreview.validPageCount} 个有效页面</h3>
                <p className="text-xs text-slate-500">{crawlPreview.status === 'PARTIAL_COMPLETED' ? `部分完成：${crawlPreview.stopReason || '达到资源限制'}` : '抓取完成'}；无效/重复页面 {crawlPreview.rejectedCount} 个</p></div>
              <button type="button" onClick={() => void handleDownloadArchive()} className="px-3 py-2 rounded-lg bg-slate-700 text-white text-sm">下载溯源 MD</button>
            </div>
            <div className="max-h-96 overflow-auto divide-y divide-slate-200 dark:divide-slate-700">
              {crawlPreview.pages.map(page => <label key={page.id} className="flex items-start gap-3 p-4 hover:bg-slate-50 dark:hover:bg-slate-700/40">
                <input type="checkbox" checked={selectedPages.has(page.id)} onChange={() => setSelectedPages(current => { const next = new Set(current); next.has(page.id) ? next.delete(page.id) : next.add(page.id); return next; })}/>
                <span className="min-w-0 flex-1"><span className="block font-medium text-slate-800 dark:text-white">{page.title}</span><span className="block text-xs text-slate-500 break-all">深度 {page.depth} · {page.characterCount.toLocaleString()} 字符 · {page.url}</span></span>
                <button type="button" onClick={event => { event.preventDefault(); downloadMarkdown(page.filename, page.markdown); }} className="text-xs text-indigo-600">下载</button>
              </label>)}
            </div>
            <div className="p-4 flex justify-end"><button type="button" onClick={() => void handleImportCrawl()} disabled={webLoading || selectedPages.size === 0} className="px-4 py-2 rounded-lg bg-emerald-500 text-white disabled:opacity-50">确认导入选中页面（{selectedPages.size}）</button></div>
          </div>
        )}
      </section>
    </div>
  );
}
