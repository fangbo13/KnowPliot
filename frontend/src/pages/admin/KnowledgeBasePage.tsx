/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, Table, Button, Space, Upload, message, Modal, Input, Alert, Tag, Drawer, Tabs, Spin, Tooltip, Select, Switch } from 'antd';
import {
  InboxOutlined,
  DownloadOutlined,
  ReloadOutlined,
  UploadOutlined,
  EditOutlined,
  FileTextOutlined,
  HistoryOutlined,
  SaveOutlined,
  RollbackOutlined,
  FileAddOutlined,
  CloudUploadOutlined,
  DeleteOutlined,
  TagsOutlined,
  SendOutlined,
  CheckCircleOutlined,
  ApartmentOutlined,
  FieldTimeOutlined,
  DashboardOutlined,
  AuditOutlined,
  TagOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import {
  ALLOWED_DOCUMENT_EXTENSIONS,
  documentApi,
  isSupportedDocumentFile,
} from '../../api/documents';
import { reviewApi, taxonomyApi } from '../../api/knowledge';
import type { TaxonomyDimension } from '../../api/knowledge';
import { useAuthorization, useCapabilities } from '../../auth/CapabilityProvider';
import { MarkdownEditor } from '../../components/knowledge/MarkdownEditor';
import { DiffPreview } from '../../components/knowledge/DiffPreview';
import type { DiffPreviewData } from '../../components/knowledge/DiffPreview';
import { TagSelector, missingRequiredDimensions } from '../../components/knowledge/TagSelector';
import { TaxonomyFilterPanel } from '../../components/knowledge/TaxonomyFilterPanel';
import { ReviewQueuePanel } from '../../components/knowledge/ReviewQueuePanel';
import { KnowledgeGraphPanel } from '../../components/knowledge/KnowledgeGraphPanel';
import { TimelinePanel } from '../../components/knowledge/TimelinePanel';
import { DashboardPanel } from '../../components/knowledge/DashboardPanel';
import { TaxonomyManagerPanel } from '../../components/knowledge/TaxonomyManagerPanel';
import { BacklinksPanel } from '../../components/knowledge/BacklinksPanel';
import GuestOnboardingBanner from '../../components/knowledge/GuestOnboardingBanner';
import { useSpaceStore } from '../../store/spaceStore';
import { spacesApi } from '../../api/spaces';
import { ActionBar, AppShell, EmptyState, PageHeader, Surface } from '../../design/primitives';

interface Document {
  id: string;
  title: string;
  file_type: string;
  status: string;
  chunk_count: number;
  category_name?: string;
  created_at: string;
  // KB-12-Features §4: version metadata fields returned by DocumentSerializer
  text_content?: string;
  version?: number;
  parent_document?: string | null;
  effective_from?: string;
  effective_to?: string | null;
  // Knowledge iteration spec §3: watermark + taxonomy metadata
  updated_at?: string;
  updated_by_name?: string | null;
  uploaded_by_name?: string | null;
  taxonomy_terms?: Array<{ id: string; code: string; label: string; dimension: string }>;
}

/** KB-12-Features §2: Version info returned by GET /documents/{id}/versions/ */
interface VersionInfo {
  id: string;
  version: number;
  status: string;
  effective_from: string;
  effective_to: string | null;
  created_at: string;
  title?: string;
}

// Bug#6/#21: theme-aware tag colours via CSS variables (auto dark-mode adaptation)
const tagStyleMap: Record<string, { bg: string; text: string; border: string }> = {
  active: { bg: 'rgba(var(--color-success-rgb), 0.12)', text: 'var(--color-success)', border: 'rgba(var(--color-success-rgb), 0.3)' },
  processing: { bg: 'rgba(var(--color-accent-rgb), 0.12)', text: 'var(--color-accent)', border: 'rgba(var(--color-accent-rgb), 0.3)' },
  failed: { bg: 'rgba(var(--color-error-rgb), 0.12)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.3)' },
  draft: { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border)' },
  uploading: { bg: 'rgba(var(--color-warning-rgb), 0.12)', text: 'var(--color-warning)', border: 'rgba(var(--color-warning-rgb), 0.3)' },
  expired: { bg: 'var(--color-fill)', text: 'var(--color-text-tertiary)', border: 'var(--color-border-secondary)' },
  stale: { bg: 'rgba(var(--color-warning-rgb), 0.12)', text: 'var(--color-warning)', border: 'rgba(var(--color-warning-rgb), 0.3)' },
  archived: { bg: 'var(--color-fill)', text: 'var(--color-text-tertiary)', border: 'var(--color-border)' },
  // Knowledge iteration spec §3: review-gate states
  pending_review: { bg: 'rgba(var(--color-accent-rgb), 0.12)', text: 'var(--color-accent)', border: 'rgba(var(--color-accent-rgb), 0.3)' },
  rejected: { bg: 'rgba(var(--color-error-rgb), 0.12)', text: 'var(--color-error)', border: 'rgba(var(--color-error-rgb), 0.3)' },
  superseded: { bg: 'var(--color-fill)', text: 'var(--color-text-tertiary)', border: 'var(--color-border-secondary)' },
};

export default function KnowledgeBasePage() {
  const { t } = useTranslation('common');
  const access = useAuthorization();
  const capabilityState = useCapabilities();
  const { getActiveSpace, loadSpaces } = useSpaceStore();
  const activeSpace = getActiveSpace();
  const spaceId = activeSpace?.id;
  // KB optimization spec §2.1/§3.2: taxonomy mode + platform admin flag.
  const taxonomyMode = activeSpace?.taxonomy_mode ?? 'inherit';
  const canRead = access.has('knowledge.read');
  const canManage = access.has('knowledge.manage');
  const canIndex = access.has('knowledge.index');
  const canDownload = access.has('knowledge.download');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(false);
  // Bug#21: tutorial banner + edit modal state
  const [showTutorial, setShowTutorial] = useState(() => !localStorage.getItem('ey-kb-tutorial-dismissed'));
  const [editTarget, setEditTarget] = useState<{ id: string; title: string; category?: string } | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  // KB-12-Features §2: Version management drawer state
  const [versionDrawer, setVersionDrawer] = useState<Document | null>(null);
  const [editText, setEditText] = useState('');
  const [originalText, setOriginalText] = useState('');
  const [diffData, setDiffData] = useState<DiffPreviewData | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionSaving, setVersionSaving] = useState(false);
  const [versionReason, setVersionReason] = useState('');
  const [rollbackSaving, setRollbackSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('content');
  // KB/RAG audit spec P3 §B1: wikilink candidates incl. reference-library titles.
  const [linkTitles, setLinkTitles] = useState<string[]>([]);
  // KB-12-Features §7: Create from text state
  const [createTextOpen, setCreateTextOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState('');
  const [createText, setCreateText] = useState('');
  const [createFromTextSaving, setCreateFromTextSaving] = useState(false);
  const [templates, setTemplates] = useState<{ slug: string; name: string; description: string }[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templateContentLoading, setTemplateContentLoading] = useState(false);
  // KB-12-Features §11: Batch upload state
  const [batchUploading, setBatchUploading] = useState(false);
  const [batchResult, setBatchResult] = useState<{
    total_files: number;
    success_count: number;
    duplicate_skipped_count: number;
    failed_count: number;
    results: Array<{ status: string; title: string; document_id?: string; existing_document_id?: string; error?: string }>;
  } | null>(null);
  // Knowledge iteration spec §2: taxonomy dimensions + pivot filter + tag editor
  const [dimensions, setDimensions] = useState<TaxonomyDimension[]>([]);
  const [dimensionsLoading, setDimensionsLoading] = useState(false);
  const [filterCodes, setFilterCodes] = useState<string[]>([]);
  const [tagTarget, setTagTarget] = useState<Document | null>(null);
  const [tagValue, setTagValue] = useState<string[]>([]);
  const [tagSaving, setTagSaving] = useState(false);
  // Spec §3: contributors watermark shown in the version drawer
  const [contributors, setContributors] = useState<Array<{ id: string; name: string }>>([]);
  const [pageTab, setPageTab] = useState('documents');
  // KB settings: review policy toggle (direct_publish | require_review)
  const [reviewPolicy, setReviewPolicy] = useState<'direct_publish' | 'require_review'>(
    activeSpace?.review_policy ?? 'direct_publish',
  );
  const [policySaving, setPolicySaving] = useState(false);
  
  useEffect(() => {
    setReviewPolicy(activeSpace?.review_policy ?? 'direct_publish');
  }, [activeSpace?.review_policy]);

  // KB settings: save review policy toggle (direct_publish ↔ require_review)
  const saveReviewPolicy = useCallback(async (next: 'direct_publish' | 'require_review') => {
    if (!spaceId) return;
    setPolicySaving(true);
    try {
      await spacesApi.update(spaceId, { review_policy: next });
      await loadSpaces();
      setReviewPolicy(next);
      message.success(t('kb_policy_saved'));
    } catch {
      message.error(t('kb_policy_save_failed'));
      // revert local state to server value
      setReviewPolicy(activeSpace?.review_policy ?? 'direct_publish');
    } finally {
      setPolicySaving(false);
    }
  }, [spaceId, loadSpaces, t, activeSpace?.review_policy]);

  const loadDocuments = useCallback(async () => {
    if (!canRead) return;
    setLoading(true);
    try {
      const data = await documentApi.getDocuments();
      setDocuments(data.results || data);
    } catch {
      message.error(t('upload_error'));
    } finally {
      setLoading(false);
    }
  }, [canRead, t]);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  const loadDimensions = useCallback(() => {
    if (!canRead) return;
    setDimensionsLoading(true);
    taxonomyApi.getDimensions()
      .then(setDimensions)
      .catch(() => setDimensions([]))
      .finally(() => setDimensionsLoading(false));
  }, [canRead]);

  useEffect(() => {
    loadDimensions();
  }, [loadDimensions]);

  // P3 §B1: seed wikilink autocomplete with space + reference-library titles.
  useEffect(() => {
    if (!canRead) return;
    documentApi.getLinkSuggestions('')
      .then((data) => setLinkTitles(
        ((data?.suggestions || []) as Array<{ title: string }>).map((s) => s.title),
      ))
      .catch(() => setLinkTitles([]));
  }, [canRead]);

  // Spec §2: pivot filter — a document must carry every selected term (AND).
  const filteredDocuments = useMemo(() => {
    if (!filterCodes.length) return documents;
    return documents.filter((doc) =>
      filterCodes.every((code) => (doc.taxonomy_terms || []).some((term) => term.code === code)),
    );
  }, [documents, filterCodes]);

  // Spec §2: tag editor handlers
  const openTagEditor = async (record: Document) => {
    setTagTarget(record);
    setTagValue((record.taxonomy_terms || []).map((term) => term.id));
    try {
      const tags = await taxonomyApi.getDocumentTags(record.id);
      setTagValue(tags.map((tag) => tag.term_id));
    } catch { /* fall back to list data */ }
  };

  const handleTagSave = async () => {
    if (!tagTarget) return;
    const missing = missingRequiredDimensions(dimensions, tagValue);
    if (missing.length) {
      message.error(t('taxonomy_required_missing', { names: missing.map((d) => d.name).join(', ') }));
      return;
    }
    setTagSaving(true);
    try {
      await taxonomyApi.setDocumentTags(tagTarget.id, tagValue);
      message.success(t('taxonomy_tags_saved'));
      setTagTarget(null);
      loadDocuments();
    } catch {
      message.error(t('taxonomy_tags_failed'));
    } finally {
      setTagSaving(false);
    }
  };

  // Spec §3: explicit (re)submission for draft / rejected versions
  const handleSubmitReview = async (record: Document) => {
    try {
      await reviewApi.submitReview(record.id);
      message.success(t('review_submit_success'));
      loadDocuments();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || t('review_submit_failed'));
    }
  };

  // Spec §4 L3: owner confirms the document is still fresh (resets stale clock)
  const handleConfirmFresh = async (record: Document) => {
    try {
      await taxonomyApi.confirmFresh(record.id);
      message.success(t('kb_confirm_fresh_success'));
      loadDocuments();
    } catch {
      message.error(t('kb_confirm_fresh_failed'));
    }
  };

  const handleReindex = async (id: string) => {
    if (!canIndex) return;
    try {
      await documentApi.reindexDocument(id);
      message.success(t('reindex_success'));
      loadDocuments();
    } catch {
      message.error(t('upload_error'));
    }
  };

  const handleArchive = async (id: string) => {
    if (!canManage) return;
    try {
      await documentApi.archiveDocument(id);
      message.success(t('kb_archive_success'));
      loadDocuments();
    } catch {
      message.error(t('upload_error'));
    }
  };

  // KB-12-Features §12: Hard delete (permanent) with conflict protection
  const handleDelete = async (id: string) => {
    if (!canManage) return;
    try {
      await documentApi.deleteDocument(id);
      message.success(t('delete_success'));
      loadDocuments();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } };
      if (axiosErr?.response?.status === 409) {
        message.error(t('kb_delete_conflict'));
      } else {
        message.error(t('kb_delete_failed'));
      }
    }
  };

  const handleDownload = async (record: Document) => {
    if (!canDownload) return;
    try {
      const { blob, filename } = await documentApi.downloadDocument(
        record.id,
        record.title,
      );
      const objectUrl = URL.createObjectURL(blob);
      try {
        const anchor = window.document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = filename;
        window.document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
      message.success(t('download_success'));
    } catch {
      message.error(t('download_error'));
    }
  };

  // Bug#21: edit document metadata
  const handleEditOpen = (record: Document) => {
    setEditTarget({ id: record.id, title: record.title, category: record.category_name });
    setEditTitle(record.title);
    setEditCategory(record.category_name || '');
  };

  const handleEditSave = async () => {
    if (!editTarget) return;
    setEditSaving(true);
    try {
      await documentApi.updateDocument(editTarget.id, { title: editTitle, category_name: editCategory });
      message.success(t('kb_update_success'));
      setEditTarget(null);
      loadDocuments();
    } catch {
      message.error(t('kb_update_failed'));
    } finally {
      setEditSaving(false);
    }
  };

  const dismissTutorial = () => {
    localStorage.setItem('ey-kb-tutorial-dismissed', 'true');
    setShowTutorial(false);
  };

  // KB-12-Features §11: Batch ZIP upload handler
  const handleBatchUpload = async (file: File) => {
    if (!canManage) return;
    if (!file.name.toLowerCase().endsWith('.zip')) {
      message.error(t('kb_batch_upload_zip_only'));
      return;
    }
    setBatchUploading(true);
    try {
      const result = await documentApi.batchUpload(file);
      setBatchResult(result);
      message.success(t('kb_batch_upload_success'));
      loadDocuments();
    } catch {
      message.error(t('kb_batch_upload_failed'));
    } finally {
      setBatchUploading(false);
    }
  };

  const confirmArchive = (id: string, title: string) => {
    if (!canManage) return;
    Modal.confirm({
      title: t('archive_confirm'),
      content: t('archive_confirm_content').replace('%s', title),
      okText: t('archive'),
      cancelText: t('cancel'),
      onOk: () => handleArchive(id),
    });
  };

  // KB-12-Features §12: Delete confirmation (permanent, danger)
  const confirmDelete = (id: string) => {
    if (!canManage) return;
    Modal.confirm({
      title: t('delete_confirm'),
      content: t('kb_delete_confirm'),
      okText: t('delete'),
      okType: 'danger',
      cancelText: t('cancel'),
      onOk: () => handleDelete(id),
    });
  };

  // KB-12-Features §2: Version management handlers
  const openVersionDrawer = (record: Document) => {
    setVersionDrawer(record);
    setEditText(record.text_content || '');
    setOriginalText(record.text_content || '');
    setDiffData(null);
    setDiffError(null);
    setVersionReason('');
    setActiveTab('content');
    setContributors([]);
    void loadVersions(record.id);
    // Spec §3: contributors watermark aggregated across the version chain
    documentApi.getDocument(record.id)
      .then((doc) => setContributors(doc.contributors || []))
      .catch(() => undefined);
  };

  const closeVersionDrawer = () => {
    setVersionDrawer(null);
    setDiffData(null);
    setDiffError(null);
    setVersionReason('');
  };

  const loadVersions = async (id: string) => {
    setVersionsLoading(true);
    try {
      const data = await documentApi.getVersions(id);
      setVersions(data.versions || data.results || data || []);
    } catch {
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  };

  const handlePreviewDiff = async () => {
    if (!versionDrawer) return;
    setDiffLoading(true);
    setDiffError(null);
    try {
      const data = await documentApi.previewDiff(versionDrawer.id, editText);
      setDiffData(data);
    } catch (err) {
      setDiffError(err instanceof Error ? err.message : t('kb_version_failed'));
    } finally {
      setDiffLoading(false);
    }
  };

  const handleCreateVersion = async () => {
    if (!versionDrawer) return;
    setVersionSaving(true);
    try {
      const resp = await documentApi.createVersion(versionDrawer.id, {
        text_content: editText,
        reason: versionReason || undefined,
      });
      // Spec §3: in require_review spaces the new version is parked at
      // pending_review and only enters the AI index after approval.
      if (resp && resp.pending_review) {
        message.info(t('kb_version_pending_review'));
        setVersionReason('');
        setDiffData(null);
        setOriginalText(editText);
        void loadVersions(versionDrawer.id);
        loadDocuments();
        return;
      }
      message.success(t('kb_version_created'));
      setVersionReason('');
      setDiffData(null);
      setOriginalText(editText);
      // Update drawer to point to the new current version so that
      // subsequent rollback / version-list calls target the right document.
      if (resp && resp.id) {
        setVersionDrawer(prev => prev
          ? { ...prev, id: resp.id, version: resp.version ?? prev.version, status: 'active' }
          : prev,
        );
        void loadVersions(resp.id);
      } else {
        void loadVersions(versionDrawer.id);
      }
      loadDocuments();
    } catch {
      message.error(t('kb_version_failed'));
    } finally {
      setVersionSaving(false);
    }
  };

  const handleRollback = (record: VersionInfo) => {
    if (!versionDrawer || !canManage) return;
    Modal.confirm({
      title: t('kb_rollback_confirm', { number: record.version }),
      okText: t('kb_rollback'),
      cancelText: t('cancel'),
      onOk: async () => {
        setRollbackSaving(true);
        try {
          const resp = await documentApi.rollbackVersion(versionDrawer.id, {
            target_version_id: record.id,
          });
          message.success(t('kb_rollback_success'));
          // Update drawer to point to the new current version so that
          // subsequent version-list / edit calls target the right document.
          const newId = resp?.id ?? versionDrawer.id;
          const newVersion = resp?.version ?? versionDrawer.version;
          setVersionDrawer(prev => prev
            ? { ...prev, id: newId, version: newVersion, status: 'active' }
            : prev,
          );
          void loadVersions(newId);
          loadDocuments();
          try {
            const doc = await documentApi.getDocument(newId);
            setEditText(doc.text_content || '');
            setOriginalText(doc.text_content || '');
          } catch {
            // keep current text if fetch fails
          }
        } catch {
          message.error(t('kb_rollback_failed'));
        } finally {
          setRollbackSaving(false);
        }
      },
    });
  };

  // KB-12-Features §7: Create from text handlers
  const openCreateText = () => {
    setCreateTextOpen(true);
    setCreateTitle('');
    setCreateText('# Untitled Document\n\n');
    void loadTemplatesForCreate();
  };

  const loadTemplatesForCreate = async () => {
    setTemplatesLoading(true);
    try {
      const data = await documentApi.getDocumentTemplates();
      setTemplates(data.templates || []);
    } catch {
      setTemplates([]);
    } finally {
      setTemplatesLoading(false);
    }
  };

  const handleTemplateSelect = async (slug: string | undefined) => {
    if (!slug) {
      setCreateText('# Untitled Document\n\n');
      return;
    }
    setTemplateContentLoading(true);
    try {
      const data = await documentApi.getDocumentTemplate(slug);
      setCreateText(data.content || '');
    } catch {
      // keep current content on error
    } finally {
      setTemplateContentLoading(false);
    }
  };

  const handleCreateFromText = async () => {
    if (!createTitle.trim() && !createText.trim()) {
      message.warning(t('kb_create_from_text_empty'));
      return;
    }
    // Prevent creating a document with a duplicate title
    const trimmedTitle = createTitle.trim();
    if (trimmedTitle) {
      const isDuplicate = documents.some(
        (doc) => doc.title.toLowerCase() === trimmedTitle.toLowerCase(),
      );
      if (isDuplicate) {
        message.warning(t('kb_create_from_text_duplicate'));
        return;
      }
    }
    setCreateFromTextSaving(true);
    try {
      const result = await documentApi.createFromText({
        title: createTitle.trim() || 'Untitled',
        text_content: createText,
      });
      message.success(t('kb_create_from_text_success'));
      setCreateTextOpen(false);
      setCreateTitle('');
      setCreateText('');
      loadDocuments();
      // Auto-open version drawer to continue the versioning flow (edit → preview diff → create version)
      if (result && result.id) {
        const newDoc: Document = {
          id: result.id,
          title: result.title || createTitle.trim() || 'Untitled',
          file_type: result.file_type || 'md',
          status: result.status || 'processing',
          chunk_count: result.chunk_count || 0,
          created_at: result.created_at || new Date().toISOString(),
          text_content: result.text_content || createText,
          version: result.version || 1,
        };
        openVersionDrawer(newDoc);
      }
    } catch {
      message.error(t('kb_create_from_text_failed'));
    } finally {
      setCreateFromTextSaving(false);
    }
  };

  const MAX_FILE_SIZE_MB = 50;

  const beforeUpload = (file: File) => {
    if (!canManage) return Upload.LIST_IGNORE;
    if (!isSupportedDocumentFile(file.name)) {
      message.error(t('file_type_error'));
      return Upload.LIST_IGNORE;
    }
    const isLt50M = file.size / 1024 / 1024 < MAX_FILE_SIZE_MB;
    if (!isLt50M) {
      message.error(t('file_size_error', { maxSize: MAX_FILE_SIZE_MB }));
      return Upload.LIST_IGNORE;
    }
    return true;
  };

  if (!canRead) return null;

  const statusLabels: Record<string, string> = {
    active: t('status_active'),
    processing: t('status_processing'),
    failed: t('status_failed'),
    draft: t('status_draft'),
    uploading: t('status_uploading'),
    expired: t('status_expired'),
    stale: t('status_stale'),
    archived: t('status_archived'),
    pending_review: t('status_pending_review'),
    rejected: t('status_rejected'),
    superseded: t('status_superseded'),
  };

  const columns: ColumnsType<Document> = [
    { title: t('kb_title'), dataIndex: 'title', key: 'title', ellipsis: true },
    { title: t('kb_category'), dataIndex: 'category_name', key: 'category', width: 140 },
    { title: t('kb_type'), dataIndex: 'file_type', key: 'file_type', width: 90 },
    { title: t('kb_chunks'), dataIndex: 'chunk_count', key: 'chunk_count', width: 90 },
    {
      title: t('kb_status'),
      dataIndex: 'status',
      key: 'status',
      width: 130,
      render: (status: string) => {
        const style = tagStyleMap[status] || { bg: 'var(--color-fill)', text: 'var(--color-text-secondary)', border: 'var(--color-border-secondary)' };
        return (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '4px 12px',
            borderRadius: '999px',
            fontSize: '12px',
            fontWeight: 500,
            background: style.bg,
            color: style.text,
            border: `1px solid ${style.border}`,
            lineHeight: 1,
            whiteSpace: 'nowrap'
          }}>
            {statusLabels[status] || status}
          </span>
        );
      },
    },
    {
      // Spec §2: controlled-vocabulary tags (科目 × FY × 阶段 × SCOT)
      title: t('kb_tags'),
      key: 'taxonomy_terms',
      width: 220,
      render: (_: unknown, record: Document) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {(record.taxonomy_terms || []).map((term) => (
            <Tooltip key={term.id} title={term.dimension}>
              <Tag style={{ marginInlineEnd: 0 }}>{term.label}</Tag>
            </Tooltip>
          ))}
        </div>
      ),
    },
    {
      // Spec §3: updater watermark "v{N} · {name} · {date}"
      title: t('kb_watermark'),
      key: 'watermark',
      width: 200,
      render: (_: unknown, record: Document) => (
        <span style={{ fontSize: 12, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
          v{record.version ?? 1} · {record.updated_by_name || record.uploaded_by_name || '—'} · {record.updated_at ? new Date(record.updated_at).toLocaleDateString() : '—'}
        </span>
      ),
    },
    { title: t('kb_created'), dataIndex: 'created_at', key: 'created_at', width: 180 },
  ];

  if (canDownload || canIndex || canManage) {
    columns.push({
      title: t('kb_actions'),
      key: 'actions',
      width: 320,
      render: (_: unknown, record: Document) => (
        <Space size="small">
          {canDownload && (
            <Button
              size="small"
              icon={<DownloadOutlined />}
              aria-label={t('download')}
              title={t('download')}
              onClick={() => handleDownload(record)}
              style={{ borderRadius: 6 }}
            />
          )}
          {canIndex && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => handleReindex(record.id)}
              disabled={record.status === 'processing'}
              aria-label={t('reindex')}
              title={t('reindex')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEditOpen(record)}
              disabled={record.status === 'archived'}
              aria-label={t('kb_edit')}
              title={t('kb_edit')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (
            <Tooltip title={t('kb_versions')}>
              <Button
                size="small"
                icon={<HistoryOutlined />}
                onClick={() => openVersionDrawer(record)}
                aria-label={t('kb_versions')}
                style={{ borderRadius: 6 }}
              />
            </Tooltip>
          )}
          {canManage && (
            <Button
              size="small"
              icon={<TagsOutlined />}
              onClick={() => void openTagEditor(record)}
              aria-label={t('kb_tags')}
              title={t('kb_tags')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (record.status === 'draft' || record.status === 'rejected') && (
            <Button
              size="small"
              icon={<SendOutlined />}
              onClick={() => void handleSubmitReview(record)}
              aria-label={t('kb_submit_review')}
              title={t('kb_submit_review')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (record.status === 'stale' || record.status === 'active') && (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => void handleConfirmFresh(record)}
              aria-label={t('kb_confirm_fresh')}
              title={t('kb_confirm_fresh')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (
            <Button
              size="small"
              icon={<InboxOutlined />}
              onClick={() => confirmArchive(record.id, record.title)}
              disabled={record.status === 'archived'}
              aria-label={t('archive')}
              title={t('archive')}
              style={{ borderRadius: 6 }}
            />
          )}
          {canManage && (
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => confirmDelete(record.id)}
              aria-label={t('delete')}
              title={t('delete')}
              style={{ borderRadius: 6 }}
            />
          )}
        </Space>
      ),
    });
  }

  return (
    <AppShell as="section" width="management" className="kp-knowledge-workbench">
        <PageHeader
          eyebrow={t('workspace_management')}
          title={t('nav_knowledge')}
          description={t('admin_knowledge_subtitle')}
        />
        {activeSpace?.my_role === 'guest' && spaceId ? (
          <GuestOnboardingBanner
            spaceId={spaceId}
            onCompleted={async () => {
              await loadSpaces();
              capabilityState.refresh();
            }}
          />
        ) : null}
        {/* Spec §2/§3/§5: documents / review queue / graph / timeline / dashboard.
            KB read-only access spec: browse-only roles (guest/reviewer) see the
            read tabs; management tabs require quality/manage capabilities. */}
        <Tabs
          activeKey={pageTab}
          onChange={setPageTab}
          style={{ marginBottom: 8 }}
          items={[
            { key: 'documents', label: (<span><AuditOutlined /> {t('kb_tab_documents')}</span>) },
            ...(access.has('quality.review') || canManage
              ? [{ key: 'review', label: (<span><CheckCircleOutlined /> {t('kb_tab_review')}</span>) }]
              : []),
            { key: 'graph', label: (<span><ApartmentOutlined /> {t('kb_tab_graph')}</span>) },
            { key: 'timeline', label: (<span><FieldTimeOutlined /> {t('kb_tab_timeline')}</span>) },
            ...(access.has('quality.read') || canManage
              ? [{ key: 'dashboard', label: (<span><DashboardOutlined /> {t('kb_tab_dashboard')}</span>) }]
              : []),
            // Taxonomy remains space-scoped; reference libraries moved to a
            // top-level personal entry.
            ...(canManage
              ? [{ key: 'taxonomy', label: (<span><TagOutlined /> {t('kb_tab_taxonomy')}</span>) }]
              : []),
            // KB settings tab: visible to space owners / knowledge managers
            ...(canManage
              ? [{ key: 'settings', label: (<span><SettingOutlined /> {t('kb_tab_settings')}</span>) }]
              : []),
          ]}
        />
        {!canManage && (
          <Alert
            type="info"
            showIcon
            message={t('kb_readonly_notice')}
            style={{ marginBottom: 16 }}
          />
        )}
        {pageTab === 'review' && (
          <Card styles={{ body: { padding: '24px' } }} className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }}>
            <ReviewQueuePanel onDecided={loadDocuments} />
          </Card>
        )}
        {pageTab === 'graph' && (
          <Card styles={{ body: { padding: '24px' } }} className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }}>
            <KnowledgeGraphPanel dimensions={dimensions} />
          </Card>
        )}
        {pageTab === 'timeline' && (
          <Card styles={{ body: { padding: '24px' } }} className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }}>
            <TimelinePanel />
          </Card>
        )}
        {pageTab === 'dashboard' && (
          <Card styles={{ body: { padding: '24px' } }} className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }}>
            <DashboardPanel />
          </Card>
        )}
        {pageTab === 'taxonomy' && (
          <Card styles={{ body: { padding: '24px' } }} className="glass-panel" style={{ borderRadius: 'var(--radius-lg)' }}>
            <TaxonomyManagerPanel
              taxonomyMode={taxonomyMode}
              canManage={canManage}
              onChanged={loadDimensions}
            />
          </Card>
        )}
        {pageTab === 'settings' && (
          <Card styles={{ body: { padding: '28px 28px 24px' } }} className="glass-panel hover-lift" style={{ borderRadius: 'var(--radius-lg)' }}>
            <div style={{ marginBottom: 24 }}>
              <span style={{ fontFamily: 'var(--font-family-display)', fontWeight: 500, fontSize: 18, color: 'var(--color-text)' }}>
                {t('kb_settings_title')}
              </span>
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'space-between',
                gap: 24,
                padding: '20px 0',
                borderTop: '1px solid var(--color-border-secondary)',
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500, fontSize: 15, color: 'var(--color-text)', marginBottom: 6 }}>
                  {t('kb_review_switch_label')}
                </div>
                <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                  {t('kb_review_switch_desc')}
                </div>
                <div style={{ fontSize: 12, color: 'var(--color-text-tertiary)', marginTop: 8 }}>
                  {reviewPolicy === 'require_review'
                    ? t('kb_review_switch_on')
                    : t('kb_review_switch_off')}
                </div>
              </div>
              <Switch
                checked={reviewPolicy === 'require_review'}
                loading={policySaving}
                onChange={(checked) => {
                  void saveReviewPolicy(checked ? 'require_review' : 'direct_publish');
                }}
              />
            </div>
          </Card>
        )}
        {pageTab === 'documents' && (
        <Surface as="section" className="kp-knowledge-documents glass-panel">
          <ActionBar
            className="kp-knowledge-actions"
            secondary={<h2>{t('document_list') || 'Document List'}</h2>}
            primary={(
              <Space size="middle" wrap>
              {canManage && (
                <Upload
                  customRequest={async ({ file, onError, onSuccess }) => {
                    try {
                      const result = await documentApi.uploadDocument(file as File);
                      onSuccess?.(result);
                    } catch (error) {
                      onError?.(
                        error instanceof Error
                          ? error
                          : new Error('Document upload failed'),
                      );
                    }
                  }}
                  accept={ALLOWED_DOCUMENT_EXTENSIONS.join(',')}
                  beforeUpload={beforeUpload}
                  showUploadList={false}
                  onChange={(info) => {
                    if (info.file.status === 'done') {
                      message.success(t('upload_success'));
                      loadDocuments();
                    } else if (info.file.status === 'error') {
                      message.error(t('upload_error'));
                    }
                  }}
                >
                  <Button type="primary" icon={<UploadOutlined />} aria-label={t('upload')} style={{ borderRadius: 8 }} className="btn-press">
                    {t('upload')}
                  </Button>
                </Upload>
              )}
              {canManage && (
                <Button
                  icon={<FileAddOutlined />}
                  onClick={openCreateText}
                  aria-label={t('kb_create_from_text')}
                  style={{ borderRadius: 8 }}
                  className="btn-press"
                >
                  {t('kb_create_from_text')}
                </Button>
              )}
              {canManage && (
                <Upload
                  accept=".zip"
                  showUploadList={false}
                  beforeUpload={(file) => {
                    void handleBatchUpload(file as File);
                    return false;
                  }}
                >
                  <Button
                    icon={<CloudUploadOutlined />}
                    loading={batchUploading}
                    aria-label={t('kb_batch_upload')}
                    title={t('kb_batch_upload_desc')}
                    style={{ borderRadius: 8 }}
                    className="btn-press"
                  >
                    {t('kb_batch_upload')}
                  </Button>
                </Upload>
              )}
              {canManage && (
                <Tag icon={<FileTextOutlined />} style={{ borderRadius: 6, border: '1px solid rgba(var(--color-accent-rgb), 0.3)', background: 'rgba(var(--color-accent-rgb), 0.08)', color: 'var(--color-accent)' }}>
                  {t('kb_md_recommended')}
                </Tag>
              )}
              <Button icon={<ReloadOutlined />} aria-label={t('refresh')} onClick={loadDocuments} style={{ borderRadius: 8 }} className="btn-press">
                {t('refresh')}
              </Button>
              </Space>
            )}
          />

          {showTutorial && canManage && (
            <Alert
              type="info"
              showIcon
              icon={<FileTextOutlined />}
              message={t('kb_upload_tutorial_title')}
              description={t('kb_upload_tutorial_desc')}
              closable
              onClose={dismissTutorial}
              action={
                <button className="msg-action-btn" onClick={dismissTutorial} style={{ whiteSpace: 'nowrap' }}>
                  {t('kb_upload_tutorial_dismiss')}
                </button>
              }
              style={{ marginBottom: 16 }}
            />
          )}

          <div className="kp-knowledge-task-layout">
            {/* Spec §2: multi-dimension pivot filter (科目 × FY × 阶段 × SCOT) */}
            <aside className="kp-knowledge-filter-rail" aria-label={t('kb_tags')}>
              <TaxonomyFilterPanel
                dimensions={dimensions}
                loading={dimensionsLoading}
                selectedCodes={filterCodes}
                onChange={setFilterCodes}
              />
            </aside>
            <div className="kp-knowledge-table-region">
              <Table
                columns={columns}
                dataSource={filteredDocuments}
                loading={loading}
                rowKey="id"
                pagination={{ pageSize: 10 }}
                scroll={{ x: 'max-content' }}
                locale={{
                  emptyText: (
                    <EmptyState
                      className="section-enter"
                      icon={<FileTextOutlined />}
                      title={t('no_documents') || 'No documents'}
                    />
                  ),
                }}
              />
            </div>
          </div>
        </Surface>
        )}

        {editTarget && (
          <Modal
            open
            title={t('kb_edit_title')}
            okText={t('kb_save')}
            cancelText={t('kb_cancel')}
            confirmLoading={editSaving}
            onOk={handleEditSave}
            onCancel={() => setEditTarget(null)}
          >
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_document_title')}</label>
              <Input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} placeholder={t('kb_document_title')} />
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_document_category')}</label>
              <Input value={editCategory} onChange={(e) => setEditCategory(e.target.value)} placeholder={t('kb_document_category')} />
            </div>
          </Modal>
        )}

        {/* Spec §2: controlled-vocabulary tag editor (required dimensions enforced) */}
        {tagTarget && (
          <Modal
            open
            title={`${tagTarget.title} — ${t('kb_tags')}`}
            okText={t('kb_save')}
            cancelText={t('cancel')}
            confirmLoading={tagSaving}
            onOk={handleTagSave}
            onCancel={() => setTagTarget(null)}
          >
            <TagSelector dimensions={dimensions} value={tagValue} onChange={setTagValue} />
          </Modal>
        )}

        {versionDrawer && (
          <Drawer
            title={`${versionDrawer.title} — ${t('kb_versions')}`}
            open
            width={720}
            onClose={closeVersionDrawer}
            destroyOnClose
          >
            {/* Spec §3: updater watermark + contributors across the version chain */}
            <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--color-text-secondary)' }}>
              <Tag color="blue">
                v{versionDrawer.version ?? 1} · {versionDrawer.updated_by_name || versionDrawer.uploaded_by_name || '—'} · {versionDrawer.updated_at ? new Date(versionDrawer.updated_at).toLocaleDateString() : '—'}
              </Tag>
              {contributors.length > 0 && (
                <span>{t('kb_contributors')}: {contributors.map((c) => c.name).join(', ')}</span>
              )}
            </div>
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                {
                  key: 'content',
                  label: t('kb_edit_content'),
                  children: (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      <MarkdownEditor
                        value={editText}
                        onChange={setEditText}
                        readOnly={!canManage}
                        placeholder={t('kb_editor_placeholder')}
                        minHeight={280}
                        linkCandidates={Array.from(new Set([
                          ...documents
                            .filter((d) => d.id !== versionDrawer?.id)
                            .map((d) => d.title),
                          ...linkTitles,
                        ]))}
                      />
                      {/* KB optimization spec §5.4: Obsidian-style backlinks */}
                      {versionDrawer && (
                        <BacklinksPanel
                          documentId={versionDrawer.id}
                          refreshKey={versions.length}
                          onOpenDocument={(docId) => {
                            const target = documents.find((d) => d.id === docId);
                            if (target) void openVersionDrawer(target);
                          }}
                        />
                      )}
                      {canManage && (
                        <>
                          <div style={{ display: 'flex', gap: 8 }}>
                            <Button
                              icon={<FileTextOutlined />}
                              onClick={handlePreviewDiff}
                              loading={diffLoading}
                              disabled={editText === originalText}
                            >
                              {t('kb_diff_preview')}
                            </Button>
                            <Button
                              type="primary"
                              icon={<SaveOutlined />}
                              onClick={handleCreateVersion}
                              loading={versionSaving}
                              disabled={editText === originalText}
                            >
                              {t('kb_editor_save_version')}
                            </Button>
                          </div>
                          <Input.TextArea
                            value={versionReason}
                            onChange={(e) => setVersionReason(e.target.value)}
                            placeholder={t('kb_diff_reason_placeholder')}
                            autoSize={{ minRows: 2, maxRows: 4 }}
                          />
                          {(diffData || diffLoading || diffError) && (
                            <DiffPreview
                              data={diffData}
                              loading={diffLoading}
                              error={diffError}
                            />
                          )}
                        </>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'versions',
                  label: t('kb_versions'),
                  children: (
                    <Spin spinning={versionsLoading}>
                      {versions.length === 0 ? (
                        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-text-tertiary)' }}>
                          {t('no_documents') || 'No versions'}
                        </div>
                      ) : (
                        <Space direction="vertical" style={{ width: '100%' }}>
                          {versions.map((v) => (
                            <Card
                              key={v.id}
                              size="small"
                              style={{
                                borderColor: 'var(--color-border)',
                                background: 'var(--color-bg-container)',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div>
                                  <Space size="small">
                                    <Tag color="blue">{t('kb_version')} {v.version}</Tag>
                                    <Tag>{v.status}</Tag>
                                  </Space>
                                  <div style={{ marginTop: 8, fontSize: 13, color: 'var(--color-text-secondary)' }}>
                                    <div>{t('kb_effective_from')}: {v.effective_from ? new Date(v.effective_from).toLocaleString() : '—'}</div>
                                    <div>{t('kb_effective_to')}: {v.effective_to ? new Date(v.effective_to).toLocaleString() : '—'}</div>
                                    <div>{t('kb_created')}: {new Date(v.created_at).toLocaleString()}</div>
                                  </div>
                                </div>
                                {canManage && (
                                  <Button
                                    size="small"
                                    icon={<RollbackOutlined />}
                                    onClick={() => handleRollback(v)}
                                    loading={rollbackSaving}
                                    disabled={v.version === versionDrawer.version}
                                  >
                                    {t('kb_rollback')}
                                  </Button>
                                )}
                              </div>
                            </Card>
                          ))}
                        </Space>
                      )}
                    </Spin>
                  ),
                },
              ]}
            />
          </Drawer>
        )}

        {createTextOpen && (
          <Modal
            open
            title={t('kb_create_from_text')}
            okText={t('kb_create_from_text')}
            cancelText={t('cancel')}
            confirmLoading={createFromTextSaving}
            onOk={handleCreateFromText}
            onCancel={() => setCreateTextOpen(false)}
            width={800}
            maskClosable={false}
          >
            <Spin spinning={templateContentLoading}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_create_from_text_template')}</label>
                <Select
                  style={{ width: '100%' }}
                  allowClear
                  placeholder={t('kb_create_from_text_template')}
                  loading={templatesLoading}
                  options={templates.map((tpl) => ({ value: tpl.slug, label: tpl.name }))}
                  onChange={handleTemplateSelect}
                />
              </div>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_document_title')}</label>
                <Input
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  placeholder={t('kb_document_title')}
                />
              </div>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 500 }}>{t('kb_edit_content')}</label>
                <MarkdownEditor
                  value={createText}
                  onChange={setCreateText}
                  placeholder={t('kb_editor_placeholder')}
                  minHeight={300}
                  linkCandidates={Array.from(new Set([...documents.map((d) => d.title), ...linkTitles]))}
                />
              </div>
            </Spin>
          </Modal>
        )}

        {batchResult && (
          <Modal
            open
            title={t('kb_batch_result')}
            okText={t('close')}
            cancelButtonProps={{ style: { display: 'none' } }}
            onOk={() => setBatchResult(null)}
            onCancel={() => setBatchResult(null)}
            width={640}
          >
            <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <Tag color="blue">{t('kb_batch_total', { count: batchResult.total_files })}</Tag>
              <Tag color="green">{t('kb_batch_success_count', { count: batchResult.success_count })}</Tag>
              <Tag color="orange">{t('kb_batch_skipped_count', { count: batchResult.duplicate_skipped_count })}</Tag>
              <Tag color="red">{t('kb_batch_failed_count', { count: batchResult.failed_count })}</Tag>
            </div>
            {batchResult.results.length > 0 && (
              <Table
                size="small"
                dataSource={batchResult.results}
                rowKey={(_, idx) => String(idx)}
                pagination={false}
                scroll={{ y: 300 }}
                columns={[
                  {
                    title: t('kb_document_title'),
                    dataIndex: 'title',
                    key: 'title',
                  },
                  {
                    title: t('kb_batch_status'),
                    dataIndex: 'status',
                    key: 'status',
                    width: 120,
                    render: (status: string) => {
                      const statusMap: Record<string, { color: string; text: string }> = {
                        success: { color: 'green', text: t('kb_batch_status_success') },
                        duplicate_skipped: { color: 'orange', text: t('kb_batch_status_duplicate') },
                        failure: { color: 'red', text: t('kb_batch_status_failure') },
                      };
                      const s = statusMap[status] || { color: 'default', text: status };
                      return <Tag color={s.color}>{s.text}</Tag>;
                    },
                  },
                ]}
              />
            )}
          </Modal>
        )}
    </AppShell>
  );
}
