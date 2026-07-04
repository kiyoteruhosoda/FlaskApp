import React, { useEffect, useState } from 'react';
import { Badge, Button, Col, Dropdown, Form, Row } from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import { MediaTag } from '../types/api';

// メディア検索条件（タグ・撮影日時・メディア種別）
export interface MediaSearchFilters {
  type: '' | 'photo' | 'video';
  tagIds: number[];
  // 撮影日時範囲（<input type="date"> の yyyy-mm-dd）
  after: string;
  before: string;
}

export const EMPTY_MEDIA_SEARCH_FILTERS: MediaSearchFilters = {
  type: '',
  tagIds: [],
  after: '',
  before: '',
};

// GET /api/media のクエリパラメータへ変換する
export function toMediaQueryParams(filters: MediaSearchFilters): {
  type?: 'photo' | 'video';
  tags?: string;
  after?: string;
  before?: string;
} {
  const params: { type?: 'photo' | 'video'; tags?: string; after?: string; before?: string } = {};
  if (filters.type) params.type = filters.type;
  if (filters.tagIds.length > 0) params.tags = filters.tagIds.join(',');
  // 撮影日時はその日全体を含む範囲にする
  if (filters.after) params.after = `${filters.after}T00:00:00`;
  if (filters.before) params.before = `${filters.before}T23:59:59`;
  return params;
}

export function hasActiveFilters(filters: MediaSearchFilters): boolean {
  return Boolean(filters.type || filters.tagIds.length > 0 || filters.after || filters.before);
}

interface MediaSearchBarProps {
  filters: MediaSearchFilters;
  onChange: (filters: MediaSearchFilters) => void;
}

// タグ・撮影日時・メディア種別でメディアを絞り込む検索バー
const MediaSearchBar: React.FC<MediaSearchBarProps> = ({ filters, onChange }) => {
  const { t } = useTranslation();
  const [allTags, setAllTags] = useState<MediaTag[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiClient.getTags({ limit: 200 });
        if (!cancelled) setAllTags(data.items);
      } catch {
        /* タグ取得失敗時はタグフィルタなしで続行 */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const toggleTag = (tagId: number) => {
    const tagIds = filters.tagIds.includes(tagId)
      ? filters.tagIds.filter((id) => id !== tagId)
      : [...filters.tagIds, tagId];
    onChange({ ...filters, tagIds });
  };

  const selectedTags = allTags.filter((tag) => filters.tagIds.includes(tag.id));

  return (
    <div data-testid="media-search-bar">
      <Row className="g-2 align-items-end">
        <Col xs={6} md="auto">
          <Form.Label className="small text-muted mb-1">{t('Media type')}</Form.Label>
          <Form.Select
            size="sm"
            value={filters.type}
            data-testid="media-type-filter"
            onChange={(e) => onChange({ ...filters, type: e.target.value as MediaSearchFilters['type'] })}
          >
            <option value="">{t('All')}</option>
            <option value="photo">{t('Photos')}</option>
            <option value="video">{t('Videos')}</option>
          </Form.Select>
        </Col>
        <Col xs={6} md="auto">
          <Form.Label className="small text-muted mb-1">{t('Tags')}</Form.Label>
          <Dropdown autoClose="outside">
            <Dropdown.Toggle
              variant="outline-secondary"
              size="sm"
              className="w-100"
              data-testid="media-tag-filter"
            >
              <i className="fa-solid fa-tags me-1" />
              {filters.tagIds.length > 0
                ? t('{{count}} tag(s)', { count: filters.tagIds.length })
                : t('Select tags')}
            </Dropdown.Toggle>
            <Dropdown.Menu style={{ maxHeight: 280, overflowY: 'auto', minWidth: 220 }} className="px-3 py-2">
              {allTags.length === 0 ? (
                <div className="text-muted small">{t('No tags available')}</div>
              ) : (
                allTags.map((tag) => (
                  <Form.Check
                    key={tag.id}
                    type="checkbox"
                    id={`media-search-tag-${tag.id}`}
                    label={tag.attr ? `${tag.name} (${tag.attr})` : tag.name}
                    checked={filters.tagIds.includes(tag.id)}
                    onChange={() => toggleTag(tag.id)}
                    data-testid="media-search-tag-option"
                  />
                ))
              )}
            </Dropdown.Menu>
          </Dropdown>
        </Col>
        <Col xs={6} md="auto">
          <Form.Label className="small text-muted mb-1">{t('Shot after')}</Form.Label>
          <Form.Control
            size="sm"
            type="date"
            value={filters.after}
            max={filters.before || undefined}
            data-testid="media-shot-after"
            onChange={(e) => onChange({ ...filters, after: e.target.value })}
          />
        </Col>
        <Col xs={6} md="auto">
          <Form.Label className="small text-muted mb-1">{t('Shot before')}</Form.Label>
          <Form.Control
            size="sm"
            type="date"
            value={filters.before}
            min={filters.after || undefined}
            data-testid="media-shot-before"
            onChange={(e) => onChange({ ...filters, before: e.target.value })}
          />
        </Col>
        {hasActiveFilters(filters) && (
          <Col xs="auto">
            <Button
              variant="outline-secondary"
              size="sm"
              onClick={() => onChange({ ...EMPTY_MEDIA_SEARCH_FILTERS })}
              data-testid="media-search-clear"
            >
              <i className="fa-solid fa-xmark me-1" />
              {t('Clear filters')}
            </Button>
          </Col>
        )}
      </Row>
      {selectedTags.length > 0 && (
        <div className="d-flex flex-wrap gap-1 mt-2">
          {selectedTags.map((tag) => (
            <Badge
              key={tag.id}
              bg="secondary"
              role="button"
              onClick={() => toggleTag(tag.id)}
              title={t('Remove tag filter')}
            >
              {tag.name} <i className="fa-solid fa-xmark ms-1" />
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
};

export default MediaSearchBar;
