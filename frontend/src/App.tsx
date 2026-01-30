import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Provider } from 'react-redux';
import { store } from './store';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from './store';
import { getCurrentUser } from './store/authSlice';

// Components
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import ToastNotification from './components/ToastNotification';

// Pages
import LoginPage from './pages/LoginPage';
import RoleSelectionPage from './pages/RoleSelectionPage';
import MediaGalleryPage from './pages/MediaGalleryPage';

// Bootstrap CSS
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.css';

// Protected Route Component
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, isLoading, user } = useSelector((state: RootState) => state.auth);

  console.log('[ProtectedRoute] isAuthenticated:', isAuthenticated, 'isLoading:', isLoading, 'user:', user);

  if (isLoading) {
    console.log('[ProtectedRoute] Loading...');
    return (
      <div className="d-flex justify-content-center align-items-center vh-100">
        <div className="spinner-border" role="status">
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    console.log('[ProtectedRoute] Not authenticated, redirecting to /login');
  }

  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />;
};

// Layout Component
const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useSelector((state: RootState) => state.auth);

  return (
    <div className="d-flex flex-column min-vh-100">
      <Header />
      {isAuthenticated ? (
        <div className="d-flex flex-grow-1">
          <Sidebar />
          <main className="flex-grow-1 overflow-auto">
            {children}
          </main>
        </div>
      ) : (
        <main className="flex-grow-1">
          {children}
        </main>
      )}
      <ToastNotification />
    </div>
  );
};

// Main App Component
const AppContent: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { isAuthenticated, user } = useSelector((state: RootState) => state.auth);

  console.log('[AppContent] isAuthenticated:', isAuthenticated, 'user:', user);

  useEffect(() => {
    // アクセストークンがある場合、かつユーザー情報がまだない場合のみ取得
    const token = localStorage.getItem('access_token');
    console.log('[AppContent useEffect] token:', token ? 'exists' : 'none', 'user:', user);
    
    if (token && !user) {
      console.log('[AppContent useEffect] Fetching current user...');
      dispatch(getCurrentUser());
    }
  }, [dispatch, user]);

  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Layout>
        <Routes>
          {/* Public Routes */}
          <Route 
            path="/login" 
            element={
              isAuthenticated ? (
                <>
                  {console.log('[Route /login] Already authenticated, redirecting to /')}
                  <Navigate to="/" />
                </>
              ) : (
                <>
                  {console.log('[Route /login] Not authenticated, showing LoginPage')}
                  <LoginPage />
                </>
              )
            } 
          />
          <Route path="/select-role" element={<RoleSelectionPage />} />

          {/* Protected Routes */}
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <div className="container py-4">
                  <h1>Welcome to PhotoNest</h1>
                  <p>Your family photo management platform</p>
                </div>
              </ProtectedRoute>
            } 
          />
          
          <Route 
            path="/dashboard" 
            element={
              <ProtectedRoute>
                <div className="container py-4">
                  <h1>Dashboard</h1>
                  <p>Your dashboard content will be displayed here</p>
                </div>
              </ProtectedRoute>
            } 
          />
          
          <Route 
            path="/profile" 
            element={
              <ProtectedRoute>
                <div className="container py-4">
                  <h1>Profile</h1>
                  <p>Your profile settings will be displayed here</p>
                </div>
              </ProtectedRoute>
            } 
          />
          
          <Route 
            path="/media" 
            element={
              <ProtectedRoute>
                <MediaGalleryPage />
              </ProtectedRoute>
            } 
          />

          {/* Catch all route */}
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Layout>
    </Router>
  );
};

// Root App Component with Provider
const App: React.FC = () => {
  return (
    <Provider store={store}>
      <AppContent />
    </Provider>
  );
};

export default App;