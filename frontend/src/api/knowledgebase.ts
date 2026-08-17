import {request} from './request';

export type VectorStatus = 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'DELETING' | 'DELETE_FAILED';
export type SortOption = 'time' | 'size';

export interface KnowledgeBaseItem {
  id: number;
  name: string;
  category: string | null;
  originalFilename: string;
  fileSize: number;
  contentType: string;
  uploadedAt: string;
  updatedAt: string;
  vectorStatus: VectorStatus;
  vectorError: string | null;
  chunkCount: number;
  sourceUrl?: string | null;
  sourceTitle?: string | null;
  sourceFetchedAt?: string | null;
  sourceHash?: string | null;
}

export interface KnowledgeBaseStats {
  totalCount: number;
  completedCount: number;
  processingCount: number;
  failedCount: number;
}

export interface UploadKnowledgeBaseResponse {
  knowledgeBase: {
    id: number;
    name: string;
    category: string;
    fileSize: number;
    contentLength: number;
  };
}

export interface WebFetchResult {
  url: string;
  title: string;
  fetchedAt: string;
  contentHash: string;
  markdown: string;
  contentType: string;
  characterCount: number;
}

export interface WebCrawlPage extends WebFetchResult {
  id: string;
  depth: number;
  parentUrl: string | null;
  filename: string;
}

export interface WebCrawlResult {
  previewToken: string;
  expiresAt: string;
  entryUrl: string;
  status: 'COMPLETED' | 'PARTIAL_COMPLETED';
  stopReason: string | null;
  validPageCount: number;
  rejectedCount: number;
  pages: WebCrawlPage[];
  rejected: Array<{url: string; reason: string}>;
}

export interface WebCrawlImportResult {
  importRunId: string;
  importedCount: number;
  knowledgeBases: Array<{id: number; name: string; filename: string; vectorStatus: VectorStatus}>;
}

export const knowledgeBaseApi = {
  async uploadKnowledgeBase(file: File, name?: string, category?: string, source?: Pick<WebFetchResult, 'url' | 'title' | 'fetchedAt' | 'contentHash'>): Promise<UploadKnowledgeBaseResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (name) formData.append('name', name);
    if (category) formData.append('category', category);
    if (source) {
      formData.append('sourceUrl', source.url);
      formData.append('sourceTitle', source.title);
      formData.append('sourceFetchedAt', source.fetchedAt);
      formData.append('sourceHash', source.contentHash);
    }
    return request.upload<UploadKnowledgeBaseResponse>('/api/knowledgebase/upload', formData);
  },

  async fetchWebPage(url: string): Promise<WebFetchResult> {
    return request.post<WebFetchResult>('/api/tools/web/fetch', {url});
  },

  async crawlWebSite(url: string, topic?: string): Promise<WebCrawlResult> {
    return request.post<WebCrawlResult>('/api/tools/web/crawl', {url, topic}, {timeout: 660000});
  },

  async importWebCrawl(previewToken: string, selectedPageIds: string[], category?: string): Promise<WebCrawlImportResult> {
    return request.post<WebCrawlImportResult>('/api/tools/web/crawl/import', {
      previewToken, selectedPageIds, category,
    }, {timeout: 300000});
  },

  async downloadWebCrawlArchive(previewToken: string): Promise<Blob> {
    const response = await request.getInstance().get(
      `/api/tools/web/crawl/${encodeURIComponent(previewToken)}/archive`,
      {responseType: 'blob', skipResultTransform: true} as never,
    );
    return response.data;
  },

  async downloadKnowledgeBase(id: number): Promise<Blob> {
    const response = await request.getInstance().get(`/api/knowledgebase/${id}/download`, {
      responseType: 'blob',
      skipResultTransform: true,
    } as never);
    return response.data;
  },

  async getAllKnowledgeBases(sortBy?: SortOption, vectorStatus?: VectorStatus): Promise<KnowledgeBaseItem[]> {
    const params = new URLSearchParams();
    if (sortBy) params.append('sortBy', sortBy);
    if (vectorStatus) params.append('vectorStatus', vectorStatus);
    const query = params.toString();
    return request.get<KnowledgeBaseItem[]>(`/api/knowledgebase/list${query ? `?${query}` : ''}`);
  },

  async deleteKnowledgeBase(id: number): Promise<void> {
    return request.delete(`/api/knowledgebase/${id}`);
  },

  async getAllCategories(): Promise<string[]> {
    return request.get<string[]>('/api/knowledgebase/categories');
  },

  async getByCategory(category: string): Promise<KnowledgeBaseItem[]> {
    return request.get<KnowledgeBaseItem[]>(`/api/knowledgebase/category/${encodeURIComponent(category)}`);
  },

  async updateCategory(id: number, category: string | null): Promise<void> {
    return request.put(`/api/knowledgebase/${id}/category`, {category});
  },

  async search(keyword: string): Promise<KnowledgeBaseItem[]> {
    return request.get<KnowledgeBaseItem[]>(`/api/knowledgebase/search?keyword=${encodeURIComponent(keyword)}`);
  },

  async getStatistics(): Promise<KnowledgeBaseStats> {
    return request.get<KnowledgeBaseStats>('/api/knowledgebase/stats');
  },

  async revectorize(id: number): Promise<void> {
    return request.post(`/api/knowledgebase/${id}/revectorize`);
  },
};
