import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Container,
  Form,
  InputGroup,
  Nav,
  Row,
  Spinner,
} from 'react-bootstrap';
import { useTranslation } from 'react-i18next';
import { apiClient } from '../services/api';
import {
  ConfigField,
  ConfigResponse,
  ConfigSection,
  SigningGroup,
} from '../types/api';

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

const SECRET_PATTERN = /(SECRET|PASSWORD|ACCESS_KEY|API_TOKEN|API_KEY|CLIENT_SECRET|SAS_TOKEN|ENCRYPTION_KEY|SIGNING_KEY|CONNECTION_STRING)/;

const isSecretField = (key: string) => SECRET_PATTERN.test(key);

type DraftValue = string | boolean;

const initialDraft = (field: ConfigField): DraftValue => {
  if (field.data_type === 'boolean') return field.form_value === 'true';
  return field.form_value;
};

const defaultDraft = (field: ConfigField): DraftValue => {
  // default_json is a JSON-encoded representation of the default value
  if (field.data_type === 'boolean') return field.default_json === 'true';
  if (!field.default_json) return field.data_type === 'list' ? '' : '';
  try {
    const parsed = JSON.parse(field.default_json);
    if (Array.isArray(parsed)) return parsed.join('\n');
    if (typeof parsed === 'boolean') return parsed;
    return String(parsed);
  } catch {
    return field.default_json;
  }
};

const toTypedValue = (field: ConfigField, draft: DraftValue): any => {
  if (field.data_type === 'boolean') return Boolean(draft);
  if (field.data_type === 'list') {
    return String(draft)
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }
  return draft;
};

const SECTION_ICONS: Record<string, string> = {
  security: 'fa-lock',
  sessions: 'fa-cookie',
  platform: 'fa-microchip',
  internationalization: 'fa-language',
  identity: 'fa-id-badge',
  downloads: 'fa-link',
  storage: 'fa-server',
  celery: 'fa-gears',
  'media-processing': 'fa-film',
  mail: 'fa-envelope',
  cdn: 'fa-globe',
  blob: 'fa-cloud',
  custom: 'fa-puzzle-piece',
  cors: 'fa-shield-halved',
  signing: 'fa-key',
};

// ---------------------------------------------------------------------------
// Field editor
// ---------------------------------------------------------------------------

interface FieldEditorProps {
  field: ConfigField;
  draft: DraftValue;
  modified: boolean;
  onChange: (value: DraftValue) => void;
  onReset: () => void;
}

const FieldEditor: React.FC<FieldEditorProps> = ({ field, draft, modified, onChange, onReset }) => {
  const { t } = useTranslation();
  const [showSecret, setShowSecret] = useState(false);
  const secret = isSecretField(field.key);

  const renderControl = () => {
    if (!field.editable) {
      return (
        <Form.Control
          plaintext
          readOnly
          value={field.current_json}
          className="font-monospace small text-muted border rounded px-2"
        />
      );
    }

    if (field.data_type === 'boolean') {
      return (
        <Form.Check
          type="switch"
          id={`switch-${field.key}`}
          checked={Boolean(draft)}
          onChange={(e) => onChange(e.target.checked)}
          label={Boolean(draft) ? t('Enabled') : t('Disabled')}
          data-testid={`config-field-${field.key}`}
        />
      );
    }

    if (field.choices && field.choices.length > 0) {
      return (
        <Form.Select
          value={String(draft)}
          onChange={(e) => onChange(e.target.value)}
          data-testid={`config-field-${field.key}`}
        >
          {field.choices.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Form.Select>
      );
    }

    if (field.multiline || field.data_type === 'list') {
      return (
        <Form.Control
          as="textarea"
          rows={3}
          value={String(draft)}
          onChange={(e) => onChange(e.target.value)}
          className="font-monospace small"
          placeholder={field.data_type === 'list' ? t('One value per line') : ''}
          data-testid={`config-field-${field.key}`}
        />
      );
    }

    if (secret) {
      return (
        <InputGroup>
          <Form.Control
            type={showSecret ? 'text' : 'password'}
            value={String(draft)}
            onChange={(e) => onChange(e.target.value)}
            autoComplete="new-password"
            className="font-monospace small"
            data-testid={`config-field-${field.key}`}
          />
          <Button variant="outline-secondary" onClick={() => setShowSecret((v) => !v)} tabIndex={-1}>
            <i className={`fa-solid ${showSecret ? 'fa-eye-slash' : 'fa-eye'}`} />
          </Button>
        </InputGroup>
      );
    }

    return (
      <Form.Control
        type={field.data_type === 'integer' || field.data_type === 'float' ? 'number' : 'text'}
        step={field.data_type === 'float' ? 'any' : undefined}
        value={String(draft)}
        onChange={(e) => onChange(e.target.value)}
        data-testid={`config-field-${field.key}`}
      />
    );
  };

  return (
    <div className={`config-field py-3 ${modified ? 'border-start border-3 border-warning ps-3' : ''}`} id={field.anchor_id}>
      <Row className="align-items-start g-2">
        <Col lg={5}>
          <div className="d-flex align-items-center gap-2 flex-wrap">
            <span className="fw-semibold">{field.label}</span>
            {field.required && <Badge bg="light" text="dark" className="border">{t('Required')}</Badge>}
            {!field.editable && <Badge bg="secondary">{t('Read-only')}</Badge>}
            {modified && <Badge bg="warning" text="dark" data-testid={`config-modified-${field.key}`}>{t('Modified')}</Badge>}
            {field.editable && !field.using_default && !modified && (
              <Badge bg="info-subtle" text="dark" className="border">{t('Overridden')}</Badge>
            )}
          </div>
          <code className="d-block text-muted small mt-1">{field.key}</code>
          {field.description && <div className="text-muted small mt-1">{field.description}</div>}
          {field.default_hint && (
            <div className="text-muted small mt-1 fst-italic">
              <i className="fa-solid fa-circle-info me-1" />{field.default_hint}
            </div>
          )}
        </Col>
        <Col lg={7}>
          {renderControl()}
          {field.editable && (
            <div className="d-flex justify-content-end mt-1">
              {!field.using_default && (
                <Button
                  variant="link"
                  size="sm"
                  className="text-muted p-0 text-decoration-none"
                  onClick={onReset}
                  data-testid={`config-reset-${field.key}`}
                >
                  <i className="fa-solid fa-rotate-left me-1" />{t('Reset to default')}
                </Button>
              )}
            </div>
          )}
        </Col>
      </Row>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const ConfigPage: React.FC = () => {
  const { t } = useTranslation();

  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [drafts, setDrafts] = useState<Record<string, DraftValue>>({});
  const [resetKeys, setResetKeys] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [activeSection, setActiveSection] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  // CORS state
  const [corsDraft, setCorsDraft] = useState('');
  const [corsSaving, setCorsSaving] = useState(false);

  // Signing state
  const [signingMode, setSigningMode] = useState('builtin');
  const [signingSecret, setSigningSecret] = useState('');
  const [signingGroup, setSigningGroup] = useState('');
  const [signingSaving, setSigningSaving] = useState(false);
  const [showSigningSecret, setShowSigningSecret] = useState(false);

  const hydrate = useCallback((data: ConfigResponse) => {
    setConfig(data);
    const newDrafts: Record<string, DraftValue> = {};
    data.application_fields.forEach((f) => {
      newDrafts[f.key] = initialDraft(f);
    });
    setDrafts(newDrafts);
    setResetKeys(new Set());

    const corsField = data.cors_fields.find((f) => f.key === 'allowedOrigins');
    setCorsDraft(corsField ? corsField.form_value : '');

    if (data.signing_setting) {
      setSigningMode(data.signing_setting.mode === 'server_signing' ? 'server_signing' : 'builtin');
      setSigningGroup(data.signing_setting.group_code || '');
    }
    setSigningSecret('');
    if (data.warnings) setWarnings(data.warnings);
  }, []);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getConfig();
      hydrate(data);
    } catch (e: any) {
      if (e?.response?.status === 403) setForbidden(true);
      else setError(e?.response?.data?.message || e?.message || t('Failed to load configuration'));
    } finally {
      setIsLoading(false);
    }
  }, [hydrate, t]);

  useEffect(() => {
    load();
  }, [load]);

  // ----- modified detection -----
  const modifiedKeys = useMemo(() => {
    if (!config) return new Set<string>();
    const set = new Set<string>();
    config.application_fields.forEach((f) => {
      if (!f.editable) return;
      if (resetKeys.has(f.key)) {
        set.add(f.key);
        return;
      }
      if (drafts[f.key] !== initialDraft(f)) set.add(f.key);
    });
    return set;
  }, [config, drafts, resetKeys]);

  const handleFieldChange = (field: ConfigField, value: DraftValue) => {
    setDrafts((prev) => ({ ...prev, [field.key]: value }));
    setResetKeys((prev) => {
      if (!prev.has(field.key)) return prev;
      const next = new Set(prev);
      next.delete(field.key);
      return next;
    });
  };

  const handleFieldReset = (field: ConfigField) => {
    setDrafts((prev) => ({ ...prev, [field.key]: defaultDraft(field) }));
    setResetKeys((prev) => new Set(prev).add(field.key));
  };

  const handleDiscard = () => {
    if (config) hydrate(config);
    setSuccessMsg(null);
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    setWarnings([]);
    try {
      const updates: Record<string, any> = {};
      const resets: string[] = [];
      config.application_fields.forEach((f) => {
        if (!f.editable || !modifiedKeys.has(f.key)) return;
        if (resetKeys.has(f.key)) {
          resets.push(f.key);
        } else {
          updates[f.key] = toTypedValue(f, drafts[f.key]);
        }
      });
      const data = await apiClient.updateConfig({ updates, resetKeys: resets });
      hydrate(data);
      setSuccessMsg(t('Configuration saved successfully'));
      if (data.warnings) setWarnings(data.warnings);
    } catch (e: any) {
      const msgs = e?.response?.data?.messages;
      setError(Array.isArray(msgs) ? msgs.join(' ') : e?.response?.data?.message || e?.message || t('Failed to save configuration'));
    } finally {
      setSaving(false);
    }
  };

  const handleCorsSave = async () => {
    setCorsSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const origins = corsDraft.split('\n').map((l) => l.trim()).filter(Boolean);
      const data = await apiClient.updateConfigCors({ allowedOrigins: origins });
      hydrate(data);
      setSuccessMsg(t('CORS settings saved successfully'));
    } catch (e: any) {
      const msgs = e?.response?.data?.messages;
      setError(Array.isArray(msgs) ? msgs.join(' ') : e?.response?.data?.message || e?.message || t('Failed to save CORS settings'));
    } finally {
      setCorsSaving(false);
    }
  };

  const handleSigningSave = async () => {
    setSigningSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const payload =
        signingMode === 'builtin'
          ? { mode: 'builtin', secret: signingSecret }
          : { mode: 'server_signing', groupCode: signingGroup };
      const data = await apiClient.updateConfigSigning(payload);
      hydrate(data);
      setSuccessMsg(t('Signing settings saved successfully'));
    } catch (e: any) {
      const msgs = e?.response?.data?.messages;
      setError(Array.isArray(msgs) ? msgs.join(' ') : e?.response?.data?.message || e?.message || t('Failed to save signing settings'));
    } finally {
      setSigningSaving(false);
    }
  };

  // ----- search filtering -----
  const filteredSections = useMemo<ConfigSection[]>(() => {
    if (!config) return [];
    const q = search.trim().toLowerCase();
    if (!q) return config.application_sections;
    return config.application_sections
      .map((section) => ({
        ...section,
        fields: section.fields.filter((f) => f.search_text.includes(q)),
      }))
      .filter((section) => section.fields.length > 0);
  }, [config, search]);

  const scrollToSection = (anchorId: string, identifier: string) => {
    setActiveSection(identifier);
    const el = document.getElementById(anchorId);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (forbidden) {
    return (
      <Container fluid className="py-4" data-testid="config-page">
        <Alert variant="danger">{t('You do not have permission to view this page')}</Alert>
      </Container>
    );
  }

  if (isLoading) {
    return (
      <Container fluid className="py-5 text-center">
        <Spinner animation="border" />
      </Container>
    );
  }

  const hasChanges = modifiedKeys.size > 0;

  return (
    <Container fluid className="py-4 pb-5" data-testid="config-page">
      <Row className="mb-3 align-items-center">
        <Col>
          <h1 className="h3 mb-1">{t('System Settings')}</h1>
          <p className="text-muted mb-0">{t('Manage application configuration, CORS, and token signing')}</p>
        </Col>
        <Col xs="auto">
          <Button variant="outline-secondary" size="sm" onClick={load}>
            <i className="fa-solid fa-rotate-right me-1" />{t('Reload')}
          </Button>
        </Col>
      </Row>

      {error && <Alert variant="danger" dismissible onClose={() => setError(null)} data-testid="config-error">{error}</Alert>}
      {successMsg && <Alert variant="success" dismissible onClose={() => setSuccessMsg(null)} data-testid="config-success">{successMsg}</Alert>}
      {warnings.length > 0 && (
        <Alert variant="warning" dismissible onClose={() => setWarnings([])} data-testid="config-warnings">
          <div className="fw-semibold mb-1">{t('Some changes require users to sign in again:')}</div>
          <ul className="mb-0">
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Alert>
      )}

      <Row>
        {/* Sidebar nav */}
        <Col lg={3} className="mb-3">
          <div style={{ position: 'sticky', top: 16 }}>
            <InputGroup className="mb-3">
              <InputGroup.Text><i className="fa-solid fa-magnifying-glass" /></InputGroup.Text>
              <Form.Control
                placeholder={t('Search settings...')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                data-testid="config-search"
              />
            </InputGroup>
            <Nav className="flex-column config-section-nav" variant="pills">
              {(search ? filteredSections : config?.application_sections ?? []).map((section) => (
                <Nav.Link
                  key={section.identifier}
                  active={activeSection === section.identifier}
                  onClick={() => scrollToSection(section.anchor_id, section.identifier)}
                  className="d-flex align-items-center py-2"
                  role="button"
                >
                  <i className={`fa-solid ${SECTION_ICONS[section.identifier] || 'fa-sliders'} me-2`} />
                  <span className="small">{section.label}</span>
                  <Badge bg="light" text="dark" className="ms-auto border">{section.fields.length}</Badge>
                </Nav.Link>
              ))}
              <hr className="my-2" />
              <Nav.Link onClick={() => scrollToSection('section-cors', 'cors')} className="d-flex align-items-center py-2" role="button">
                <i className="fa-solid fa-shield-halved me-2" />
                <span className="small">{t('CORS')}</span>
              </Nav.Link>
              <Nav.Link onClick={() => scrollToSection('section-signing', 'signing')} className="d-flex align-items-center py-2" role="button">
                <i className="fa-solid fa-key me-2" />
                <span className="small">{t('Token Signing')}</span>
              </Nav.Link>
            </Nav>
          </div>
        </Col>

        {/* Content */}
        <Col lg={9}>
          {filteredSections.length === 0 && search && (
            <Alert variant="light" className="text-center text-muted" data-testid="config-no-results">
              {t('No settings match your search.')}
            </Alert>
          )}

          {filteredSections.map((section) => (
            <Card className="mb-4 shadow-sm" key={section.identifier} id={section.anchor_id} data-testid={`config-section-${section.identifier}`}>
              <Card.Header className="bg-white">
                <div className="d-flex align-items-center">
                  <i className={`fa-solid ${SECTION_ICONS[section.identifier] || 'fa-sliders'} me-2 fs-5 text-primary`} />
                  <div>
                    <div className="fw-semibold">{section.label}</div>
                    {section.description && <div className="text-muted small">{section.description}</div>}
                  </div>
                </div>
              </Card.Header>
              <Card.Body className="py-0">
                {section.fields.map((field, idx) => (
                  <div key={field.key} className={idx > 0 ? 'border-top' : ''}>
                    <FieldEditor
                      field={field}
                      draft={drafts[field.key] ?? initialDraft(field)}
                      modified={modifiedKeys.has(field.key)}
                      onChange={(v) => handleFieldChange(field, v)}
                      onReset={() => handleFieldReset(field)}
                    />
                  </div>
                ))}
              </Card.Body>
            </Card>
          ))}

          {/* CORS card */}
          {!search && (
            <Card className="mb-4 shadow-sm" id="section-cors" data-testid="config-section-cors">
              <Card.Header className="bg-white">
                <div className="d-flex align-items-center">
                  <i className="fa-solid fa-shield-halved me-2 fs-5 text-primary" />
                  <div>
                    <div className="fw-semibold">{t('CORS')}</div>
                    <div className="text-muted small">{t('Cross-Origin Resource Sharing allowed origins')}</div>
                  </div>
                </div>
              </Card.Header>
              <Card.Body>
                <Form.Group>
                  <Form.Label className="fw-semibold">{t('Allowed origins')}</Form.Label>
                  <Form.Control
                    as="textarea"
                    rows={4}
                    value={corsDraft}
                    onChange={(e) => setCorsDraft(e.target.value)}
                    className="font-monospace small"
                    placeholder={'https://example.com\nhttps://app.example.com'}
                    data-testid="config-cors-origins"
                  />
                  <Form.Text className="text-muted">
                    {t('One origin per line. Use a full URL (https://example.com) or * for all.')}
                  </Form.Text>
                </Form.Group>
                {config && config.cors_effective_origins.length > 0 && (
                  <div className="mt-2">
                    <div className="text-muted small mb-1">{t('Currently effective:')}</div>
                    <div className="d-flex flex-wrap gap-1">
                      {config.cors_effective_origins.map((o) => (
                        <Badge key={o} bg="light" text="dark" className="border font-monospace">{o}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </Card.Body>
              <Card.Footer className="bg-white text-end">
                <Button variant="primary" size="sm" onClick={handleCorsSave} disabled={corsSaving} data-testid="config-cors-save">
                  {corsSaving ? <Spinner size="sm" animation="border" className="me-1" /> : <i className="fa-solid fa-check me-1" />}
                  {t('Save CORS')}
                </Button>
              </Card.Footer>
            </Card>
          )}

          {/* Signing card */}
          {!search && config && (
            <Card className="mb-4 shadow-sm" id="section-signing" data-testid="config-section-signing">
              <Card.Header className="bg-white">
                <div className="d-flex align-items-center">
                  <i className="fa-solid fa-key me-2 fs-5 text-primary" />
                  <div>
                    <div className="fw-semibold">{t('Token Signing')}</div>
                    <div className="text-muted small">{t('How access tokens are signed')}</div>
                  </div>
                </div>
              </Card.Header>
              <Card.Body>
                <Form.Check
                  type="radio"
                  id="signing-builtin"
                  name="signing-mode"
                  label={t('Built-in secret (HMAC)')}
                  checked={signingMode === 'builtin'}
                  onChange={() => setSigningMode('builtin')}
                  data-testid="config-signing-builtin"
                />
                {signingMode === 'builtin' && (
                  <div className="ms-4 my-2">
                    <Form.Label className="small fw-semibold">{t('JWT secret key')}</Form.Label>
                    <InputGroup>
                      <Form.Control
                        type={showSigningSecret ? 'text' : 'password'}
                        value={signingSecret}
                        onChange={(e) => setSigningSecret(e.target.value)}
                        placeholder={config.builtin_signing_secret ? t('Leave unchanged or enter a new secret') : t('Enter a secret key')}
                        autoComplete="new-password"
                        className="font-monospace small"
                        data-testid="config-signing-secret"
                      />
                      <Button variant="outline-secondary" onClick={() => setShowSigningSecret((v) => !v)} tabIndex={-1}>
                        <i className={`fa-solid ${showSigningSecret ? 'fa-eye-slash' : 'fa-eye'}`} />
                      </Button>
                    </InputGroup>
                    {config.builtin_signing_secret && (
                      <Form.Text className="text-muted">{t('A secret is already configured.')}</Form.Text>
                    )}
                  </div>
                )}

                <Form.Check
                  type="radio"
                  id="signing-server"
                  name="signing-mode"
                  label={t('Server signing certificate (asymmetric)')}
                  checked={signingMode === 'server_signing'}
                  onChange={() => setSigningMode('server_signing')}
                  className="mt-2"
                  data-testid="config-signing-server"
                />
                {signingMode === 'server_signing' && (
                  <div className="ms-4 my-2">
                    <Form.Label className="small fw-semibold">{t('Certificate group')}</Form.Label>
                    <Form.Select
                      value={signingGroup}
                      onChange={(e) => setSigningGroup(e.target.value)}
                      data-testid="config-signing-group"
                    >
                      <option value="">{t('Select a certificate group...')}</option>
                      {config.signingGroups.map((g: SigningGroup) => (
                        <option key={g.groupCode} value={g.groupCode} disabled={!g.latestCertificate}>
                          {g.groupLabel}
                          {!g.latestCertificate ? ` (${t('no valid certificate')})` : ''}
                        </option>
                      ))}
                    </Form.Select>
                    {config.signingGroups.length === 0 && (
                      <Form.Text className="text-danger">{t('No server signing certificate groups available.')}</Form.Text>
                    )}
                  </div>
                )}
              </Card.Body>
              <Card.Footer className="bg-white text-end">
                <Button variant="primary" size="sm" onClick={handleSigningSave} disabled={signingSaving} data-testid="config-signing-save">
                  {signingSaving ? <Spinner size="sm" animation="border" className="me-1" /> : <i className="fa-solid fa-check me-1" />}
                  {t('Save Signing')}
                </Button>
              </Card.Footer>
            </Card>
          )}
        </Col>
      </Row>

      {/* Sticky save bar for application settings */}
      {hasChanges && (
        <div
          className="position-fixed bottom-0 start-50 translate-middle-x mb-3 bg-white border shadow rounded-pill px-4 py-2 d-flex align-items-center gap-3"
          style={{ zIndex: 1040 }}
          data-testid="config-save-bar"
        >
          <span className="small">
            <Badge bg="warning" text="dark" className="me-2">{modifiedKeys.size}</Badge>
            {t('unsaved change(s)')}
          </span>
          <Button variant="outline-secondary" size="sm" onClick={handleDiscard} disabled={saving} data-testid="config-discard">
            {t('Discard')}
          </Button>
          <Button variant="primary" size="sm" onClick={handleSave} disabled={saving} data-testid="config-save">
            {saving ? <Spinner size="sm" animation="border" className="me-1" /> : <i className="fa-solid fa-check me-1" />}
            {t('Save Changes')}
          </Button>
        </div>
      )}
    </Container>
  );
};

export default ConfigPage;
