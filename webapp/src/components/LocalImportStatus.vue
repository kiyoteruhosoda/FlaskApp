<!-- Local Import状態管理UI -->
<template>
  <div class="local-import-status">
    <!-- セッション状態概要 -->
    <div class="status-overview card">
      <h3>セッション状態</h3>
      <div class="status-badge" :class="`status-${sessionStatus.state}`">
        {{ getStateLabel(sessionStatus.state) }}
      </div>
      
      <div class="stats-grid">
        <div class="stat-item">
          <span class="stat-label">全アイテム</span>
          <span class="stat-value">{{ sessionStatus.stats.total || 0 }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">成功</span>
          <span class="stat-value success">{{ sessionStatus.stats.success || 0 }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">失敗</span>
          <span class="stat-value error">{{ sessionStatus.stats.failed || 0 }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">処理中</span>
          <span class="stat-value processing">{{ sessionStatus.stats.processing || 0 }}</span>
        </div>
      </div>
      
      <div class="last-updated">
        最終更新: {{ formatDateTime(sessionStatus.last_updated) }}
      </div>
    </div>
    
    <!-- タブナビゲーション -->
    <div class="tabs">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
        <span v-if="tab.badge" class="badge">{{ tab.badge }}</span>
      </button>
    </div>
    
    <!-- エラー一覧タブ -->
    <div v-show="activeTab === 'errors'" class="tab-content">
      <div v-if="errors.length === 0" class="empty-state">
        <p>エラーはありません</p>
      </div>
      
      <div v-else class="error-list">
        <div 
          v-for="error in errors" 
          :key="error.id"
          class="error-item card"
        >
          <div class="error-header">
            <span class="error-time">{{ formatTime(error.timestamp) }}</span>
            <span v-if="error.error_type" class="error-type">{{ error.error_type }}</span>
          </div>
          
          <div class="error-message">{{ error.message }}</div>
          
          <div v-if="error.error_message" class="error-detail">
            {{ error.error_message }}
          </div>
          
          <div v-if="error.recommended_actions && error.recommended_actions.length" class="recommended-actions">
            <strong>推奨アクション:</strong>
            <ul>
              <li v-for="(action, idx) in error.recommended_actions" :key="idx">
                {{ action }}
              </li>
            </ul>
          </div>
          
          <div v-if="error.item_id" class="error-item-id">
            アイテムID: {{ error.item_id }}
          </div>
        </div>
      </div>
    </div>
    
    <!-- 状態遷移履歴タブ -->
    <div v-show="activeTab === 'transitions'" class="tab-content">
      <div v-if="transitions.length === 0" class="empty-state">
        <p>状態遷移履歴がありません</p>
      </div>
      
      <div v-else class="transition-list">
        <div 
          v-for="(transition, idx) in transitions" 
          :key="idx"
          class="transition-item"
        >
          <span class="transition-time">{{ formatTime(transition.timestamp) }}</span>
          <span class="transition-arrow">
            <span class="state-label">{{ transition.from_state }}</span>
            →
            <span class="state-label">{{ transition.to_state }}</span>
          </span>
          <span v-if="transition.reason" class="transition-reason">
            {{ transition.reason }}
          </span>
        </div>
      </div>
    </div>
    
    <!-- パフォーマンスタブ -->
    <div v-show="activeTab === 'performance'" class="tab-content">
      <div v-if="performance.metrics.length === 0" class="empty-state">
        <p>パフォーマンスデータがありません</p>
      </div>
      
      <div v-else>
        <div class="performance-summary card">
          <div class="perf-stat">
            <span class="perf-label">総操作数</span>
            <span class="perf-value">{{ performance.total_operations }}</span>
          </div>
          <div class="perf-stat">
            <span class="perf-label">総処理時間</span>
            <span class="perf-value">{{ formatDuration(performance.total_duration_ms) }}</span>
          </div>
          <div class="perf-stat">
            <span class="perf-label">平均処理時間</span>
            <span class="perf-value">{{ formatDuration(performance.avg_duration_ms) }}</span>
          </div>
        </div>
        
        <div class="performance-chart">
          <canvas ref="perfChart"></canvas>
        </div>
      </div>
    </div>
    
    <!-- トラブルシューティングタブ -->
    <div v-show="activeTab === 'troubleshooting'" class="tab-content">
      <div v-if="!troubleshooting" class="loading">
        <p>読み込み中...</p>
      </div>
      
      <div v-else class="troubleshooting-report card">
        <div class="severity-badge" :class="`severity-${troubleshooting.severity}`">
          {{ getSeverityLabel(troubleshooting.severity) }}
        </div>
        
        <div class="report-section">
          <h4>エラー概要</h4>
          <p>総エラー数: {{ troubleshooting.total_errors }}</p>
          <p v-if="troubleshooting.top_error_category">
            最も多いエラー: {{ troubleshooting.top_error_category }}
          </p>
        </div>
        
        <div v-if="troubleshooting.recommended_actions.length" class="report-section">
          <h4>推奨アクション</h4>
          <ul class="action-list">
            <li v-for="(action, idx) in troubleshooting.recommended_actions" :key="idx">
              {{ action }}
            </li>
          </ul>
        </div>
        
        <div class="report-section">
          <h4>エラーカテゴリ別集計</h4>
          <div class="error-categories">
            <div 
              v-for="(count, category) in troubleshooting.error_categories" 
              :key="category"
              class="category-item"
            >
              <span class="category-name">{{ category }}</span>
              <span class="category-count">{{ count }}</span>
            </div>
          </div>
        </div>
        
        <div class="report-section">
          <button @click="runConsistencyCheck" class="btn btn-primary">
            整合性チェックを実行
          </button>
        </div>
      </div>
    </div>
    
    <!-- 整合性チェック結果モーダル -->
    <div v-if="consistencyResult" class="modal" @click.self="consistencyResult = null">
      <div class="modal-content card">
        <h3>整合性チェック結果</h3>
        
        <div class="consistency-status" :class="{ error: !consistencyResult.is_consistent }">
          {{ consistencyResult.is_consistent ? '✓ 整合性OK' : '✗ 不整合を検出' }}
        </div>
        
        <div v-if="consistencyResult.issues.length" class="issues-section">
          <h4>問題点</h4>
          <ul>
            <li v-for="(issue, idx) in consistencyResult.issues" :key="idx" class="issue-item">
              {{ issue }}
            </li>
          </ul>
        </div>
        
        <div v-if="consistencyResult.recommendations.length" class="recommendations-section">
          <h4>推奨対応</h4>
          <ul>
            <li v-for="(rec, idx) in consistencyResult.recommendations" :key="idx" class="recommendation-item">
              {{ rec }}
            </li>
          </ul>
        </div>
        
        <button @click="consistencyResult = null" class="btn btn-secondary">
          閉じる
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'LocalImportStatus',
  
  props: {
    sessionId: {
      type: Number,
      required: true,
    },
  },
  
  data() {
    return {
      activeTab: 'errors',
      sessionStatus: {
        state: '',
        stats: {},
        last_updated: null,
      },
      errors: [],
      transitions: [],
      performance: {
        total_operations: 0,
        total_duration_ms: 0,
        avg_duration_ms: 0,
        metrics: [],
      },
      troubleshooting: null,
      consistencyResult: null,
      refreshInterval: null,
    };
  },
  
  computed: {
    tabs() {
      return [
        { id: 'errors', label: 'エラー', badge: this.errors.length },
        { id: 'transitions', label: '状態遷移', badge: null },
        { id: 'performance', label: 'パフォーマンス', badge: null },
        { id: 'troubleshooting', label: 'トラブルシューティング', badge: null },
      ];
    },
  },
  
  mounted() {
    this.loadData();
    
    // 30秒ごとに自動更新
    this.refreshInterval = setInterval(() => {
      this.loadData();
    }, 30000);
  },
  
  beforeUnmount() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
  },
  
  methods: {
    async loadData() {
      try {
        await Promise.all([
          this.loadSessionStatus(),
          this.loadErrors(),
          this.loadTransitions(),
          this.loadPerformance(),
          this.loadTroubleshooting(),
        ]);
      } catch (error) {
        console.error('データ読み込みエラー:', error);
      }
    },
    
    async loadSessionStatus() {
      const response = await fetch(`/api/local-import/sessions/${this.sessionId}/status`);
      this.sessionStatus = await response.json();
    },
    
    async loadErrors() {
      const response = await fetch(`/api/local-import/sessions/${this.sessionId}/errors`);
      const data = await response.json();
      this.errors = data.errors;
    },
    
    async loadTransitions() {
      const response = await fetch(`/api/local-import/sessions/${this.sessionId}/transitions`);
      const data = await response.json();
      this.transitions = data.transitions;
    },
    
    async loadPerformance() {
      const response = await fetch(`/api/local-import/sessions/${this.sessionId}/performance`);
      this.performance = await response.json();
    },
    
    async loadTroubleshooting() {
      const response = await fetch(`/api/local-import/sessions/${this.sessionId}/troubleshooting`);
      this.troubleshooting = await response.json();
    },
    
    async runConsistencyCheck() {
      try {
        const response = await fetch(`/api/local-import/sessions/${this.sessionId}/consistency-check`);
        this.consistencyResult = await response.json();
      } catch (error) {
        alert('整合性チェックに失敗しました: ' + error.message);
      }
    },
    
    getStateLabel(state) {
      const labels = {
        pending: '待機中',
        ready: '準備完了',
        expanding: '展開中',
        processing: '処理中',
        enqueued: 'キュー投入済み',
        importing: 'インポート中',
        imported: '完了',
        canceled: 'キャンセル',
        expired: '期限切れ',
        error: 'エラー',
        failed: '失敗',
      };
      return labels[state] || state;
    },
    
    getSeverityLabel(severity) {
      const labels = {
        low: '低',
        medium: '中',
        high: '高',
        critical: '重大',
      };
      return labels[severity] || severity;
    },
    
    formatDateTime(dateStr) {
      if (!dateStr) return '-';
      const date = new Date(dateStr);
      return date.toLocaleString('ja-JP');
    },
    
    formatTime(dateStr) {
      if (!dateStr) return '-';
      const date = new Date(dateStr);
      return date.toLocaleTimeString('ja-JP');
    },
    
    formatDuration(ms) {
      if (!ms) return '-';
      if (ms < 1000) return `${ms.toFixed(0)}ms`;
      return `${(ms / 1000).toFixed(2)}s`;
    },
  },
};
</script>

<style scoped>
.local-import-status {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  margin-bottom: 20px;
}

.status-overview {
  text-align: center;
}

.status-badge {
  display: inline-block;
  padding: 8px 16px;
  border-radius: 20px;
  font-weight: bold;
  margin: 10px 0;
}

.status-imported { background: #4caf50; color: white; }
.status-importing { background: #2196f3; color: white; }
.status-processing { background: #ff9800; color: white; }
.status-failed { background: #f44336; color: white; }
.status-error { background: #f44336; color: white; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin: 20px 0;
}

.stat-item {
  text-align: center;
}

.stat-label {
  display: block;
  font-size: 14px;
  color: #666;
}

.stat-value {
  display: block;
  font-size: 32px;
  font-weight: bold;
  margin-top: 5px;
}

.stat-value.success { color: #4caf50; }
.stat-value.error { color: #f44336; }
.stat-value.processing { color: #2196f3; }

.tabs {
  display: flex;
  gap: 10px;
  border-bottom: 2px solid #e0e0e0;
  margin-bottom: 20px;
}

.tabs button {
  padding: 10px 20px;
  border: none;
  background: none;
  cursor: pointer;
  position: relative;
}

.tabs button.active {
  color: #2196f3;
  border-bottom: 2px solid #2196f3;
  margin-bottom: -2px;
}

.badge {
  background: #f44336;
  color: white;
  border-radius: 10px;
  padding: 2px 8px;
  font-size: 12px;
  margin-left: 5px;
}

.error-list, .transition-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.error-item {
  border-left: 4px solid #f44336;
}

.error-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 14px;
  color: #666;
}

.error-type {
  background: #ffe0e0;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
}

.error-message {
  font-weight: bold;
  margin-bottom: 10px;
}

.recommended-actions {
  background: #e3f2fd;
  padding: 10px;
  border-radius: 4px;
  margin-top: 10px;
}

.recommended-actions ul {
  margin: 10px 0 0 20px;
}

.transition-item {
  padding: 10px;
  background: #f5f5f5;
  border-radius: 4px;
  display: flex;
  gap: 15px;
  align-items: center;
}

.state-label {
  background: #e0e0e0;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
}

.troubleshooting-report .severity-badge {
  display: inline-block;
  padding: 8px 16px;
  border-radius: 4px;
  font-weight: bold;
  margin-bottom: 20px;
}

.severity-low { background: #4caf50; color: white; }
.severity-medium { background: #ff9800; color: white; }
.severity-high { background: #f44336; color: white; }
.severity-critical { background: #9c27b0; color: white; }

.report-section {
  margin: 20px 0;
}

.action-list {
  list-style: none;
  padding: 0;
}

.action-list li {
  padding: 10px;
  background: #e3f2fd;
  margin: 5px 0;
  border-radius: 4px;
}

.modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
}

.consistency-status {
  padding: 20px;
  text-align: center;
  font-size: 24px;
  font-weight: bold;
  background: #4caf50;
  color: white;
  border-radius: 8px;
  margin: 20px 0;
}

.consistency-status.error {
  background: #f44336;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary {
  background: #2196f3;
  color: white;
}

.btn-secondary {
  background: #757575;
  color: white;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #999;
}
</style>
