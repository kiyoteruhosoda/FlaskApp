import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { Media, MediaSession, Album, PaginatedResponse } from '../types/api';
import { apiClient } from '../services/api';

interface MediaState {
  mediaList: Media[];
  sessions: MediaSession[];
  albums: Album[];
  currentMedia: Media | null;
  currentSession: MediaSession | null;
  currentAlbum: Album | null;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
  isLoading: boolean;
  error: string | null;
}

const initialState: MediaState = {
  mediaList: [],
  sessions: [],
  albums: [],
  currentMedia: null,
  currentSession: null,
  currentAlbum: null,
  pagination: {
    page: 1,
    pageSize: 20,
    total: 0,
    totalPages: 0,
    hasNext: false,
    hasPrev: false,
  },
  isLoading: false,
  error: null,
};

// 非同期アクション
export const fetchMediaList = createAsyncThunk(
  'media/fetchMediaList',
  async (params: {
    page?: number;
    pageSize?: number;
    session_id?: string;
    media_type?: 'photo' | 'video';
    sort?: string;
  }, { rejectWithValue }) => {
    try {
      const response = await apiClient.getMediaList(params);
      if (response.success && response.data) {
        return response as PaginatedResponse<Media>;
      }
      return rejectWithValue(response.message || 'メディアの取得に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const fetchSessionList = createAsyncThunk(
  'media/fetchSessionList',
  async (params: {
    page?: number;
    pageSize?: number;
    sort?: string;
  }, { rejectWithValue }) => {
    try {
      const response = await apiClient.getSessionList(params);
      if (response.success && response.data) {
        return response as PaginatedResponse<MediaSession>;
      }
      return rejectWithValue(response.message || 'セッションの取得に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const fetchAlbumList = createAsyncThunk(
  'media/fetchAlbumList',
  async (params: {
    page?: number;
    pageSize?: number;
    sort?: string;
  }, { rejectWithValue }) => {
    try {
      const response = await apiClient.getAlbumList(params);
      if (response.success && response.data) {
        return response as PaginatedResponse<Album>;
      }
      return rejectWithValue(response.message || 'アルバムの取得に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

export const fetchMedia = createAsyncThunk(
  'media/fetchMedia',
  async (id: string, { rejectWithValue }) => {
    try {
      const response = await apiClient.getMedia(id);
      if (response.success && response.data) {
        return response.data;
      }
      return rejectWithValue(response.message || 'メディアの取得に失敗しました');
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || 'ネットワークエラーが発生しました');
    }
  }
);

const mediaSlice = createSlice({
  name: 'media',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
    setCurrentMedia: (state, action: PayloadAction<Media | null>) => {
      state.currentMedia = action.payload;
    },
    setCurrentSession: (state, action: PayloadAction<MediaSession | null>) => {
      state.currentSession = action.payload;
    },
    setCurrentAlbum: (state, action: PayloadAction<Album | null>) => {
      state.currentAlbum = action.payload;
    },
  },
  extraReducers: (builder) => {
    // メディアリスト取得
    builder
      .addCase(fetchMediaList.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchMediaList.fulfilled, (state, action) => {
        state.isLoading = false;
        state.mediaList = action.payload.data || [];
        state.pagination = action.payload.pagination;
        state.error = null;
      })
      .addCase(fetchMediaList.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // セッションリスト取得
    builder
      .addCase(fetchSessionList.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchSessionList.fulfilled, (state, action) => {
        state.isLoading = false;
        state.sessions = action.payload.data || [];
        state.error = null;
      })
      .addCase(fetchSessionList.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // アルバムリスト取得
    builder
      .addCase(fetchAlbumList.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchAlbumList.fulfilled, (state, action) => {
        state.isLoading = false;
        state.albums = action.payload.data || [];
        state.error = null;
      })
      .addCase(fetchAlbumList.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });

    // メディア詳細取得
    builder
      .addCase(fetchMedia.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchMedia.fulfilled, (state, action) => {
        state.isLoading = false;
        state.currentMedia = action.payload;
        state.error = null;
      })
      .addCase(fetchMedia.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });
  },
});

export const { clearError, setCurrentMedia, setCurrentSession, setCurrentAlbum } = mediaSlice.actions;
export default mediaSlice.reducer;