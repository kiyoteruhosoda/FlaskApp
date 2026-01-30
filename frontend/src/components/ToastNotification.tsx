import React, { useEffect } from 'react';
import { Toast, ToastContainer } from 'react-bootstrap';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, AppDispatch } from '../store';
import { removeToast } from '../store/uiSlice';

const ToastNotification: React.FC = () => {
  const dispatch = useDispatch<AppDispatch>();
  const { toasts } = useSelector((state: RootState) => state.ui);

  const handleClose = (toastId: string) => {
    dispatch(removeToast(toastId));
  };

  return (
    <ToastContainer position="top-end" className="p-3" style={{ zIndex: 9999 }}>
      {toasts.map((toast) => (
        <ToastItem
          key={toast.id}
          toast={toast}
          onClose={() => handleClose(toast.id)}
        />
      ))}
    </ToastContainer>
  );
};

interface ToastItemProps {
  toast: {
    id: string;
    message: string;
    type: 'success' | 'error' | 'warning' | 'info';
    duration?: number;
  };
  onClose: () => void;
}

const ToastItem: React.FC<ToastItemProps> = ({ toast, onClose }) => {
  const getBgVariant = (type: string) => {
    switch (type) {
      case 'success':
        return 'success';
      case 'error':
        return 'danger';
      case 'warning':
        return 'warning';
      case 'info':
        return 'info';
      default:
        return 'light';
    }
  };

  const getIcon = (type: string) => {
    switch (type) {
      case 'success':
        return 'bi-check-circle-fill';
      case 'error':
        return 'bi-exclamation-triangle-fill';
      case 'warning':
        return 'bi-exclamation-triangle-fill';
      case 'info':
        return 'bi-info-circle-fill';
      default:
        return 'bi-info-circle-fill';
    }
  };

  useEffect(() => {
    if (toast.duration && toast.duration > 0) {
      const timer = setTimeout(() => {
        onClose();
      }, toast.duration);

      return () => clearTimeout(timer);
    }
  }, [toast.duration, onClose]);

  return (
    <Toast 
      onClose={onClose}
      bg={getBgVariant(toast.type)}
      className="text-white"
    >
      <Toast.Header>
        <i className={`bi ${getIcon(toast.type)} me-2`}></i>
        <strong className="me-auto">
          {toast.type.charAt(0).toUpperCase() + toast.type.slice(1)}
        </strong>
      </Toast.Header>
      <Toast.Body>{toast.message}</Toast.Body>
    </Toast>
  );
};

export default ToastNotification;