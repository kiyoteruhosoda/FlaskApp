import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { User, LoginRequest, RegisterRequest } from '../types/api';
import { apiClient } from '../services/api';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  redirectUrl: string | null;
}

const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  redirectUrl: null,
};

// 非同期アクション
export const login = createAsyncThunk(
  'auth/login',
  async (credentials: LoginRequest, { rejectWithValue }) => {
    try {
      const response = await apiClient.login(credentials);
      if (response.success && response.data) {
        localStorage.setItem('access_token', response.data.access_token);
        localStorage.setItem('refresh_token', response.data.refresh_token);
        // Flaskはログイン時にuserオブジェクトを返さないので、トークン情報のみ返す
        return response.data;
      }
      return rejectWithValue(response.message || 'ログインに失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.error || 'ネットワークエラーが発生しました');
    }
  }
);

export const register = createAsyncThunk(
  'auth/register',
  async (userData: RegisterRequest, { rejectWithValue }) => {
    try {
      const response = await apiClient.register(userData);
      if (response.success && response.data) {
        return response.data;
      }
      return rejectWithValue(response.message || 'アカウント作成に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const getCurrentUser = createAsyncThunk(
  'auth/getCurrentUser',
  async (_, { rejectWithValue }) => {
    try {
      const response = await apiClient.getCurrentUser();
      if (response.success && response.data) {
        return response.data;
      }
      return rejectWithValue(response.message || 'ユーザー情報の取得に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const getUserRoles = createAsyncThunk(
  'auth/getUserRoles',
  async (_, { rejectWithValue }) => {
    try {
      const response = await apiClient.getUserRoles();
      if (response.success && response.data) {
        return response.data;
      }
      return rejectWithValue(response.message || 'ロール情報の取得に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const selectRole = createAsyncThunk(
  'auth/selectRole',
  async (roleId: number, { rejectWithValue }) => {
    try {
      const response = await apiClient.selectRole(roleId);
      if (response.success && response.data) {
        return response.data;
      }
      return rejectWithValue(response.message || 'ロール選択に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const logout = createAsyncThunk(
  'auth/logout',
  async () => {
    try {
      await apiClient.logout();
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      return null;
    } catch (error: any) {
      // ログアウトは常に成功扱いにする
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      return null;
    }
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
    setUser: (state, action: PayloadAction<User>) => {
      state.user = action.payload;
      state.isAuthenticated = true;
    },
  },
  extraReducers: (builder) => {
    // ログイン
    builder
      .addCase(login.pending, (state) => {
        console.log('[authSlice] login.pending');
        state.isLoading = true;
        state.error = null;
      })
      .addCase(login.fulfilled, (state, action) => {
        console.log('[authSlice] login.fulfilled');
        state.isLoading = false;
        // Flaskはuserオブジェクトを返さないので、認証状態のみ更新
        state.isAuthenticated = true;
        state.redirectUrl = action.payload.redirect_url || null;
        state.error = null;
      })
      .addCase(login.rejected, (state, action) => {
        console.log('[authSlice] login.rejected, error:', action.payload);
        state.isLoading = false;
        state.error = action.payload as string;
        state.isAuthenticated = false;
        state.user = null;
      });

    // ユーザー登録
    builder
      .addCase(register.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(register.fulfilled, (state, action) => {
        state.isLoading = false;
        state.user = action.payload;
        state.error = null;
      })
      .addCase(register.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // 現在のユーザー取得
    builder
      .addCase(getCurrentUser.pending, (state) => {
        console.log('[authSlice] getCurrentUser.pending');
        state.isLoading = true;
      })
      .addCase(getCurrentUser.fulfilled, (state, action) => {
        console.log('[authSlice] getCurrentUser.fulfilled, user:', action.payload);
        state.isLoading = false;
        state.user = action.payload;
        state.isAuthenticated = true;
        state.error = null;
      })
      .addCase(getCurrentUser.rejected, (state, action) => {
        console.log('[authSlice] getCurrentUser.rejected, error:', action.payload);
        state.isLoading = false;
        state.error = action.payload as string;
        state.isAuthenticated = false;
        state.user = null;
      });

    // ログアウト
    builder
      .addCase(logout.fulfilled, (state) => {
        state.user = null;
        state.isAuthenticated = false;
        state.isLoading = false;
        state.error = null;
      });
  },
});

export const { clearError, setUser } = authSlice.actions;
export default authSlice.reducer;