import React, { useState, useEffect } from 'react';
import { Container, Row, Col, Card, Button, Alert, Spinner, Form } from 'react-bootstrap';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { clearError, getCurrentUser } from '../store/authSlice';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

const RoleSelectionPage: React.FC = () => {
  const { t } = useTranslation();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const { isLoading, error } = useSelector((state: RootState) => state.auth);

  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);
  const [roles, setRoles] = useState<any[]>([]);

  useEffect(() => {
    // ロール一覧を取得
    const fetchRoles = async () => {
      try {
        const response = await fetch('/api/auth/roles', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
            'Content-Type': 'application/json',
          },
        });
        
        if (response.ok) {
          const data = await response.json();
          setRoles(data.roles || []);
          
          // 既にアクティブなロールがあれば選択状態にする
          if (data.active_role_id) {
            setSelectedRoleId(data.active_role_id);
          }
          
          // ロール選択が不要な場合はダッシュボードにリダイレクト
          if (!data.requires_selection) {
            navigate('/dashboard');
          }
        }
      } catch (error) {
        console.error('Failed to fetch roles:', error);
      }
    };
    
    fetchRoles();
  }, [navigate]);

  const handleRoleSelect = async () => {
    if (!selectedRoleId) {
      return;
    }

    try {
      const response = await fetch('/api/auth/select-role', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ role_id: selectedRoleId }),
      });
      
      if (response.ok) {
        const data = await response.json();
        // ユーザー情報を再取得
        dispatch(getCurrentUser());
        // リダイレクト
        navigate(data.redirect_url || '/dashboard');
      } else {
        dispatch(clearError());
        // エラーハンドリングは適切に行う
      }
    } catch (error) {
      console.error('Role selection failed:', error);
    }
  };

  return (
    <Container fluid className="min-vh-100 d-flex align-items-center justify-content-center bg-light">
      <Row className="w-100">
        <Col md={6} lg={4} className="mx-auto">
          <Card className="shadow">
            <Card.Header className="text-center py-3">
              <h4 className="mb-0">{t('Select Role')}</h4>
              <small className="text-muted">{t('Choose your active role to continue')}</small>
            </Card.Header>
            <Card.Body className="p-4">
              {error && (
                <Alert variant="danger" dismissible onClose={() => dispatch(clearError())}>
                  {error}
                </Alert>
              )}

              <Form>
                <Form.Group className="mb-4">
                  <Form.Label>{t('Available Roles')}</Form.Label>
                  {roles.map((role) => (
                    <Form.Check
                      key={role.id}
                      type="radio"
                      name="role"
                      id={`role-${role.id}`}
                      label={
                        <div>
                          <strong>{role.name}</strong>
                          <br />
                          <small className="text-muted">
                            {t('Permissions')}: {role.permissions?.join(', ') || t('None')}
                          </small>
                        </div>
                      }
                      checked={selectedRoleId === role.id}
                      onChange={() => setSelectedRoleId(role.id)}
                      className="mb-3"
                    />
                  ))}
                </Form.Group>

                <Button
                  variant="primary"
                  onClick={handleRoleSelect}
                  className="w-100"
                  disabled={!selectedRoleId || isLoading}
                >
                  {isLoading ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-2" />
                      {t('Selecting...')}
                    </>
                  ) : (
                    t('Continue')
                  )}
                </Button>
              </Form>
            </Card.Body>
          </Card>
        </Col>
      </Row>
    </Container>
  );
};

export default RoleSelectionPage;