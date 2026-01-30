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
  const { isAuthenticated, isLoading } = useSelector((state: RootState) => state.auth);

  if (isLoading) {
    return (
      <div className="d-flex justify-content-center align-items-center vh-100">
        <div className="spinner-border" role="status">
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
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
  const { isAuthenticated } = useSelector((state: RootState) => state.auth);

  useEffect(() => {
    // アクセストークンがある場合、現在のユーザーを取得
    const token = localStorage.getItem('access_token');
    if (token && !isAuthenticated) {
      dispatch(getCurrentUser());
    }
  }, [dispatch, isAuthenticated]);

  return (
    <Router>
      <Layout>
        <Routes>
          {/* Public Routes */}
          <Route 
            path="/login" 
            element={
              isAuthenticated ? <Navigate to="/" /> : <LoginPage />
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