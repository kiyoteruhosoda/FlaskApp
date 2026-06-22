export interface WikiPage {
  id: number;
  title: string;
  content: string;
  slug: string;
  is_published: boolean;
  parent_id: number | null;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
  created_by_id: number | null;
  updated_by_id: number | null;
}

export interface WikiCategory {
  id: number;
  name: string;
  description: string | null;
  slug: string;
  sort_order: number;
  created_at: string | null;
  page_count?: number;
}

export interface WikiRevision {
  id: number;
  page_id: number;
  title: string;
  content: string;
  revision_number: number;
  change_summary: string | null;
  created_at: string | null;
  created_by_id: number | null;
}

export interface WikiPageHierarchyItem {
  id: number;
  title: string;
  slug: string;
  children?: WikiPageHierarchyItem[];
}

export interface WikiIndexData {
  recent_pages: WikiPage[];
  page_hierarchy: WikiPageHierarchyItem[];
  categories: WikiCategory[];
}

export interface WikiPageDetailData {
  page: WikiPage;
  children: WikiPageHierarchyItem[];
  categories: WikiCategory[];
  page_hierarchy: WikiPageHierarchyItem[];
}

export interface WikiCreateFormData {
  categories: WikiCategory[];
  pages: WikiPage[];
}

export interface WikiEditFormData {
  page: WikiPage;
  categories: WikiCategory[];
}

export interface WikiPageHistoryData {
  page: WikiPage;
  revisions: WikiRevision[];
}

export interface WikiCategoryDetailData {
  category: WikiCategory;
  pages: WikiPage[];
}

export interface WikiAdminData {
  total_pages: number;
  total_categories: number;
  recent_pages: WikiPage[];
}

export interface WikiCreatePageInput {
  title: string;
  content: string;
  slug?: string;
  parent_id?: number | null;
  category_ids: number[];
}

export interface WikiUpdatePageInput {
  title: string;
  content: string;
  change_summary?: string;
  category_ids: number[];
}

export interface WikiCreateCategoryInput {
  name: string;
  description?: string;
  slug?: string;
}
