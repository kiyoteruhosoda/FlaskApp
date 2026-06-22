import axios, { AxiosInstance } from 'axios';
import {
  WikiIndexData,
  WikiPageDetailData,
  WikiCreateFormData,
  WikiEditFormData,
  WikiPageHistoryData,
  WikiCategoryDetailData,
  WikiAdminData,
  WikiPage,
  WikiCategory,
  WikiRevision,
  WikiCreatePageInput,
  WikiUpdatePageInput,
  WikiCreateCategoryInput,
} from '../types/wiki';

function createWikiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: '/wiki/api',
    headers: { 'Content-Type': 'application/json' },
  });

  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      if (error.response?.status === 401) {
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          try {
            const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken });
            const newToken = res.data?.access_token || res.data?.data?.access_token;
            if (newToken) {
              localStorage.setItem('access_token', newToken);
              error.config.headers.Authorization = `Bearer ${newToken}`;
              return client.request(error.config);
            }
          } catch {
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            window.location.href = '/login';
          }
        } else {
          localStorage.removeItem('access_token');
          window.location.href = '/login';
        }
      }
      return Promise.reject(error);
    }
  );

  return client;
}

const wikiClient = createWikiClient();

export const wikiApi = {
  getIndex: async (): Promise<WikiIndexData> => {
    const res = await wikiClient.get<WikiIndexData>('/index');
    return res.data;
  },

  getPages: async (): Promise<WikiPage[]> => {
    const res = await wikiClient.get<{ pages: WikiPage[] }>('/pages');
    return res.data.pages;
  },

  getPage: async (slug: string): Promise<WikiPageDetailData> => {
    const res = await wikiClient.get<WikiPageDetailData>(`/pages/${slug}`);
    return res.data;
  },

  getCreateForm: async (): Promise<WikiCreateFormData> => {
    const res = await wikiClient.get<WikiCreateFormData>('/create-form');
    return res.data;
  },

  createPage: async (input: WikiCreatePageInput): Promise<WikiPage> => {
    const res = await wikiClient.post<{ page: WikiPage }>('/pages', input);
    return res.data.page;
  },

  getEditForm: async (slug: string): Promise<WikiEditFormData> => {
    const res = await wikiClient.get<WikiEditFormData>(`/pages/${slug}/edit-form`);
    return res.data;
  },

  updatePage: async (slug: string, input: WikiUpdatePageInput): Promise<WikiPage> => {
    const res = await wikiClient.patch<{ page: WikiPage }>(`/pages/${slug}`, input);
    return res.data.page;
  },

  deletePage: async (slug: string): Promise<void> => {
    await wikiClient.delete(`/pages/${slug}`);
  },

  getPageHistory: async (slug: string): Promise<WikiPageHistoryData> => {
    const res = await wikiClient.get<WikiPageHistoryData>(`/pages/${slug}/history`);
    return res.data;
  },

  search: async (q: string, limit = 20): Promise<{ pages: WikiPage[]; query: string }> => {
    const res = await wikiClient.get<{ pages: WikiPage[]; query: string }>('/search', {
      params: { q, limit },
    });
    return res.data;
  },

  previewMarkdown: async (content: string): Promise<string> => {
    const res = await wikiClient.post<{ html: string }>('/preview', { content });
    return res.data.html;
  },

  getCategories: async (): Promise<WikiCategory[]> => {
    const res = await wikiClient.get<{ categories: WikiCategory[] }>('/categories');
    return res.data.categories;
  },

  createCategory: async (input: WikiCreateCategoryInput): Promise<WikiCategory> => {
    const res = await wikiClient.post<{ category: WikiCategory }>('/categories', input);
    return res.data.category;
  },

  getCategory: async (slug: string): Promise<WikiCategoryDetailData> => {
    const res = await wikiClient.get<WikiCategoryDetailData>(`/categories/${slug}`);
    return res.data;
  },

  getAdminData: async (): Promise<WikiAdminData> => {
    const res = await wikiClient.get<WikiAdminData>('/admin');
    return res.data;
  },
};
