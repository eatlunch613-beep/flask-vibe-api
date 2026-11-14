/**
 * 個人記帳本前端邏輯 (Vanilla JavaScript)
 * 遵守《docs/前端串接.md》規範
 */

(function () {
  'use strict';

  // 常數與狀態
  const STORAGE_KEY = 'ledger.connection';
  let apiBaseUrl = '';
  let currentView = 'connection';

  // 暫存資料
  let cachedAccounts = [];
  let cachedIncomeCategories = [];
  let cachedExpenseCategories = [];
  let recordsActiveTab = 'expense'; // 'expense' | 'income'
  let cachedRecordsList = [];

  // DOM 元素快取
  const pageTitleEl = document.getElementById('page-title');
  const btnClearConnection = document.getElementById('btn-clear-connection');
  const bottomNav = document.getElementById('bottom-nav');
  const toastEl = document.getElementById('toast');
  const toastMessageEl = document.getElementById('toast-message');
  const toastCloseBtn = document.getElementById('toast-close');

  // 各分頁 Section
  const viewConnection = document.getElementById('view-connection');
  const viewHome = document.getElementById('view-home');
  const viewRecords = document.getElementById('view-records');
  const viewInvestments = document.getElementById('view-investments');
  const viewInvoices = document.getElementById('view-invoices');

  const views = {
    connection: viewConnection,
    home: viewHome,
    records: viewRecords,
    investments: viewInvestments,
    invoices: viewInvoices
  };

  const navButtons = {
    home: document.getElementById('nav-btn-home'),
    records: document.getElementById('nav-btn-records'),
    investments: document.getElementById('nav-btn-investments'),
    invoices: document.getElementById('nav-btn-invoices')
  };

  // ==========================================
  // 工具函式：提示訊息 (Toast)
  // ==========================================
  let toastTimer = null;
  function showToast(message, type = 'error') {
    if (toastTimer) {
      clearTimeout(toastTimer);
    }
    toastMessageEl.textContent = message || '發生未預期錯誤';
    toastEl.className = 'toast ' + (type === 'success' ? 'toast-success' : 'toast-error');
    toastEl.classList.remove('hidden');

    toastTimer = setTimeout(() => {
      toastEl.classList.add('hidden');
    }, 4500);
  }

  toastCloseBtn.addEventListener('click', () => {
    toastEl.classList.add('hidden');
  });

  // ==========================================
  // 工具函式：日期與金額格式化
  // ==========================================
  function getCurrentMonthKey() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
  }

  function getTodayDateString() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function formatTWD(num) {
    if (num === null || num === undefined || isNaN(num)) return 'NT$ 0';
    return 'NT$ ' + Number(num).toLocaleString('zh-TW', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    });
  }

  function formatQuantity(num) {
    if (num === null || num === undefined || isNaN(num)) return '0';
    return Number(num).toLocaleString('zh-TW', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 4
    });
  }

  function getAccountKindName(kind) {
    const map = {
      cash: '現金',
      bank: '銀行帳戶',
      credit_card: '信用卡',
      broker: '證券交割戶'
    };
    return map[kind] || kind || '一般帳戶';
  }

  function getPrizeStatusMeta(status) {
    const map = {
      unchecked: { label: '未對獎', cls: 'status-unchecked' },
      won: { label: '已中獎', cls: 'status-won' },
      claimed: { label: '已領獎', cls: 'status-claimed' },
      lost: { label: '未中獎', cls: 'status-lost' },
      void: { label: '已作廢', cls: 'status-void' }
    };
    return map[status] || { label: status || '未知', cls: 'status-unchecked' };
  }

  // ==========================================
  // 連線管理與 URL 正規化
  // ==========================================
  /**
   * 整理後端 URL：
   * 1. 網址必須是 http 或 https 開頭
   * 2. 當主機是 localhost 且連接埠是 5000 時，改成 127.0.0.1，避免 macOS AirPlay 接收器衝突
   * 3. 去除末尾多餘斜線
   */
  function normalizeApiUrl(rawUrl) {
    let urlStr = (rawUrl || '').trim();
    if (!urlStr.startsWith('http://') && !urlStr.startsWith('https://')) {
      throw new Error('請輸入以 http:// 或 https:// 開頭的後端網址');
    }

    try {
      const u = new URL(urlStr);
      if ((u.hostname === 'localhost' || u.hostname === '127.0.0.1') && u.port === '5000') {
        u.hostname = '127.0.0.1';
      }
      let clean = u.origin + u.pathname;
      clean = clean.replace(/\/+$/, '');
      return clean;
    } catch (e) {
      throw new Error('網址格式錯誤，請重新確認');
    }
  }

  // ==========================================
  // API 通訊核心封裝 (遵循規範 4 與 5)
  // ==========================================
  /**
   * apiRequest:
   * - 所有請求的 base URL 取自 apiBaseUrl
   * - 不附加金鑰
   * - 有正文 (POST/PATCH/PUT) 才設 Content-Type: application/json
   * - 沒有正文的 GET 不要加 Content-Type，維持 CORS 簡單請求
   * - 客戶端不送 id, created_at, updated_at
   * - GET 請求加上查詢參數 _t 當下毫秒時間，防止快取
   * - fetch 設 cache: 'no-store', mode: 'cors'
   * - 失敗時畫面只顯示 message，連不上顯示「目前連不上記帳服務」
   */
  async function apiRequest(endpoint, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    let url = `${apiBaseUrl}${endpoint}`;

    // GET 請求加入 _t 毫秒時間戳記防快取
    if (method === 'GET') {
      const separator = url.includes('?') ? '&' : '?';
      url += `${separator}_t=${Date.now()}`;
    }

    const fetchOptions = {
      method,
      mode: 'cors',
      cache: 'no-store',
      headers: {}
    };

    // 有正文才加 Content-Type: application/json
    if (options.body && method !== 'GET') {
      fetchOptions.headers['Content-Type'] = 'application/json';
      fetchOptions.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
    }

    let response;
    try {
      response = await fetch(url, fetchOptions);
    } catch (netErr) {
      // 網路中斷、無法連線、CORS 擋下或連不上伺服器
      throw new Error('目前連不上記帳服務');
    }

    // 解析 JSON
    let json;
    try {
      json = await response.json();
    } catch (parseErr) {
      throw new Error(response.ok ? '伺服器回應格式錯誤' : '目前連不上記帳服務');
    }

    // 檢查業務 code 或 HTTP 狀態碼
    if (!response.ok || (json.code && json.code >= 400)) {
      const errMsg = json.message || '目前連不上記帳服務';
      throw new Error(errMsg);
    }

    return json;
  }

  // ==========================================
  // 畫面切換控制 (Navigation)
  // ==========================================
  function switchView(viewName) {
    currentView = viewName;

    // 隱藏所有頁面
    Object.values(views).forEach(el => el.classList.add('hidden'));

    // 顯示指定頁面
    if (views[viewName]) {
      views[viewName].classList.remove('hidden');
    }

    // 控制頂端清除連線按鈕與底部導覽欄顯示狀態
    if (viewName === 'connection') {
      btnClearConnection.classList.add('hidden');
      bottomNav.classList.add('hidden');
      pageTitleEl.textContent = '個人記帳本';
    } else {
      btnClearConnection.classList.remove('hidden');
      bottomNav.classList.remove('hidden');

      // 更新分頁按鈕高亮
      Object.keys(navButtons).forEach(key => {
        if (key === viewName) {
          navButtons[key].classList.add('active');
        } else {
          navButtons[key].classList.remove('active');
        }
      });

      // 更新頂部標題
      const titles = {
        home: '首頁 - 現金流與資產',
        records: '記帳 - 收支明細',
        investments: '投資 - 台股持有與報價',
        invoices: '發票 - 統一發票夾'
      };
      pageTitleEl.textContent = titles[viewName] || '個人記帳本';

      // 觸發載入該分頁資料
      loadViewData(viewName);
    }

    // 捲動至頂部
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function loadViewData(viewName) {
    switch (viewName) {
      case 'home':
        loadHomeData();
        break;
      case 'records':
        loadRecordsData();
        break;
      case 'investments':
        loadInvestmentsData();
        break;
      case 'invoices':
        loadInvoicesData();
        break;
    }
  }

  // 註冊底部導航事件
  Object.keys(navButtons).forEach(viewName => {
    navButtons[viewName].addEventListener('click', () => {
      switchView(viewName);
    });
  });

  // 清除連線
  btnClearConnection.addEventListener('click', () => {
    localStorage.removeItem(STORAGE_KEY);
    apiBaseUrl = '';
    showToast('已清除連線資訊', 'success');
    switchView('connection');
  });

  // ==========================================
  // 1. 連線設定頁 (Connection Page)
  // ==========================================
  const formConnection = document.getElementById('form-connection');
  const inputApiUrl = document.getElementById('input-api-url');
  const btnConnect = document.getElementById('btn-connect');

  formConnection.addEventListener('submit', async (e) => {
    e.preventDefault();
    const rawUrl = inputApiUrl.value;

    let cleanUrl;
    try {
      cleanUrl = normalizeApiUrl(rawUrl);
    } catch (err) {
      showToast(err.message);
      return;
    }

    btnConnect.disabled = true;
    btnConnect.textContent = '連線測試中...';

    try {
      apiBaseUrl = cleanUrl;
      // 發送健康檢查 GET /api/health
      const res = await apiRequest('/api/health');
      if (res.code === 200 && res.data && res.data.status === 'ok') {
        // 通過檢查，存入 localStorage
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ apiBaseUrl: cleanUrl }));
        showToast('連線成功，歡迎使用個人記帳本', 'success');
        switchView('home');
      } else {
        showToast(res.message || '健康檢查未通過');
      }
    } catch (err) {
      showToast(err.message || '目前連不上記帳服務');
    } finally {
      btnConnect.disabled = false;
      btnConnect.textContent = '測試並進入記帳本';
    }
  });

  // ==========================================
  // 2. 首頁邏輯 (Home View)
  // ==========================================
  const homeMonthTag = document.getElementById('home-month-tag');
  const homeIncomeAmount = document.getElementById('home-income-amount');
  const homeExpenseAmount = document.getElementById('home-expense-amount');
  const homeAccountsList = document.getElementById('home-accounts-list');
  const homeNoAccountCard = document.getElementById('home-no-account-card');
  const formQuickAccount = document.getElementById('form-quick-account');
  const inputQuickAccountName = document.getElementById('input-quick-account-name');

  async function loadHomeData() {
    const monthKey = getCurrentMonthKey();
    homeMonthTag.textContent = monthKey;

    // 平行抓取月度摘要與帳戶清單
    await Promise.allSettled([
      fetchSummary(monthKey),
      fetchAccountsAndBalances()
    ]);
  }

  async function fetchSummary(monthKey) {
    try {
      const res = await apiRequest(`/api/summary?month=${monthKey}`);
      if (res.data) {
        homeIncomeAmount.textContent = formatTWD(res.data.income_twd);
        homeExpenseAmount.textContent = formatTWD(res.data.expense_twd);
      }
    } catch (err) {
      showToast(err.message);
    }
  }

  async function fetchAccountsAndBalances() {
    homeAccountsList.innerHTML = '<div class="loading-state">載入帳戶資訊中...</div>';
    try {
      const res = await apiRequest('/api/accounts');
      const accounts = Array.isArray(res.data) ? res.data : [];
      cachedAccounts = accounts;

      if (accounts.length === 0) {
        homeAccountsList.innerHTML = '';
        homeNoAccountCard.classList.remove('hidden');
        return;
      }

      homeNoAccountCard.classList.add('hidden');

      // 對每個帳戶並行查詢 GET /api/accounts/<id>/balance
      const balancePromises = accounts.map(acc =>
        apiRequest(`/api/accounts/${acc.id}/balance`)
          .then(balRes => ({ id: acc.id, ...balRes.data }))
          .catch(() => ({ id: acc.id, balance: 0, twd_balance: 0 }))
      );

      const balances = await Promise.all(balancePromises);
      const balanceMap = new Map(balances.map(b => [b.id, b]));

      // 渲染帳戶列表
      homeAccountsList.innerHTML = '';
      accounts.forEach(acc => {
        const balData = balanceMap.get(acc.id) || { balance: 0, twd_balance: 0 };
        const card = document.createElement('div');
        card.className = 'account-card';
        card.innerHTML = `
          <div class="account-info">
            <div class="account-name">${escapeHTML(acc.name)}</div>
            <div class="account-kind">${getAccountKindName(acc.kind)} · ${escapeHTML(acc.currency || 'TWD')}</div>
          </div>
          <div class="account-balance-box">
            <div class="account-twd-balance">${formatTWD(balData.twd_balance)}</div>
            ${acc.currency && acc.currency !== 'TWD' ? `<div class="account-orig-balance">${acc.currency} ${Number(balData.balance).toFixed(2)}</div>` : ''}
          </div>
        `;
        homeAccountsList.appendChild(card);
      });
    } catch (err) {
      homeAccountsList.innerHTML = `<div class="loading-state error-text">${escapeHTML(err.message)}</div>`;
      showToast(err.message);
    }
  }

  // 首頁建立現金帳戶表單
  formQuickAccount.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = inputQuickAccountName.value.trim();
    if (!name) {
      showToast('請輸入帳戶名稱');
      return;
    }

    try {
      const payload = {
        name,
        kind: 'cash',
        currency: 'TWD',
        opening_balance: 0.0
      };
      const res = await apiRequest('/api/accounts', {
        method: 'POST',
        body: payload
      });

      showToast(res.message || '帳戶建立成功', 'success');
      inputQuickAccountName.value = '現金錢包';
      await fetchAccountsAndBalances();
    } catch (err) {
      showToast(err.message);
    }
  });

  // ==========================================
  // 3. 記帳邏輯 (Records View)
  // ==========================================
  const tabBtnExpense = document.getElementById('tab-btn-expense');
  const tabBtnIncome = document.getElementById('tab-btn-income');
  const cardExpenseForm = document.getElementById('card-expense-form');
  const cardIncomeForm = document.getElementById('card-income-form');
  const recordsListTitle = document.getElementById('records-list-title');
  const recordsList = document.getElementById('records-list');

  // 花費表單元素
  const formExpense = document.getElementById('form-expense');
  const expSpentOn = document.getElementById('expense-spent-on');
  const expAmount = document.getElementById('expense-amount');
  const expCategory = document.getElementById('expense-category');
  const expAccount = document.getElementById('expense-account');
  const expMerchant = document.getElementById('expense-merchant');
  const expNote = document.getElementById('expense-note');
  const boxEmptyExpCat = document.getElementById('box-empty-expense-category');
  const inputQuickExpCat = document.getElementById('input-quick-exp-cat-name');
  const btnQuickCreateExpCat = document.getElementById('btn-quick-create-exp-cat');

  // 入帳表單元素
  const formIncome = document.getElementById('form-income');
  const incReceivedOn = document.getElementById('income-received-on');
  const incAmount = document.getElementById('income-amount');
  const incCategory = document.getElementById('income-category');
  const incAccount = document.getElementById('income-account');
  const incSource = document.getElementById('income-source');
  const incNote = document.getElementById('income-note');
  const boxEmptyIncCat = document.getElementById('box-empty-income-category');
  const inputQuickIncCat = document.getElementById('input-quick-inc-cat-name');
  const btnQuickCreateIncCat = document.getElementById('btn-quick-create-inc-cat');

  // 記帳頁籤切換
  tabBtnExpense.addEventListener('click', () => {
    recordsActiveTab = 'expense';
    tabBtnExpense.classList.add('active');
    tabBtnIncome.classList.remove('active');
    cardExpenseForm.classList.remove('hidden');
    cardIncomeForm.classList.add('hidden');
    recordsListTitle.textContent = '本月花費明細';
    fetchRecordsList();
  });

  tabBtnIncome.addEventListener('click', () => {
    recordsActiveTab = 'income';
    tabBtnIncome.classList.add('active');
    tabBtnExpense.classList.remove('active');
    cardIncomeForm.classList.remove('hidden');
    cardExpenseForm.classList.add('hidden');
    recordsListTitle.textContent = '本月入帳明細';
    fetchRecordsList();
  });

  async function loadRecordsData() {
    // 預設填入今日日期
    const today = getTodayDateString();
    expSpentOn.value = today;
    incReceivedOn.value = today;

    // 載入下拉選項
    await Promise.allSettled([
      fetchExpenseCategories(),
      fetchIncomeCategories(),
      refreshAccountDropdowns()
    ]);

    // 載入清單
    await fetchRecordsList();
  }

  async function refreshAccountDropdowns() {
    try {
      const res = await apiRequest('/api/accounts');
      cachedAccounts = Array.isArray(res.data) ? res.data : [];

      const opts = cachedAccounts.map(acc =>
        `<option value="${acc.id}">${escapeHTML(acc.name)} (${getAccountKindName(acc.kind)})</option>`
      ).join('');

      if (cachedAccounts.length === 0) {
        expAccount.innerHTML = '<option value="">請先至首頁建立帳戶</option>';
        incAccount.innerHTML = '<option value="">請先至首頁建立帳戶</option>';
      } else {
        expAccount.innerHTML = opts;
        incAccount.innerHTML = opts;
      }
    } catch (err) {
      showToast(err.message);
    }
  }

  async function fetchExpenseCategories() {
    try {
      const res = await apiRequest('/api/expense-categories');
      cachedExpenseCategories = Array.isArray(res.data) ? res.data : [];

      if (cachedExpenseCategories.length === 0) {
        boxEmptyExpCat.classList.remove('hidden');
        expCategory.innerHTML = '<option value="">尚未建立分類</option>';
      } else {
        boxEmptyExpCat.classList.add('hidden');
        expCategory.innerHTML = cachedExpenseCategories.map(cat =>
          `<option value="${cat.id}">${escapeHTML(cat.name)}</option>`
        ).join('');
      }
    } catch (err) {
      showToast(err.message);
    }
  }

  async function fetchIncomeCategories() {
    try {
      const res = await apiRequest('/api/income-categories');
      cachedIncomeCategories = Array.isArray(res.data) ? res.data : [];

      if (cachedIncomeCategories.length === 0) {
        boxEmptyIncCat.classList.remove('hidden');
        incCategory.innerHTML = '<option value="">尚未建立分類</option>';
      } else {
        boxEmptyIncCat.classList.add('hidden');
        incCategory.innerHTML = cachedIncomeCategories.map(cat =>
          `<option value="${cat.id}">${escapeHTML(cat.name)}</option>`
        ).join('');
      }
    } catch (err) {
      showToast(err.message);
    }
  }

  // 快速建立花費分類
  btnQuickCreateExpCat.addEventListener('click', async () => {
    const name = inputQuickExpCat.value.trim();
    if (!name) {
      showToast('請輸入花費分類名稱');
      return;
    }
    try {
      const res = await apiRequest('/api/expense-categories', {
        method: 'POST',
        body: { name }
      });
      showToast(res.message || '花費分類建立成功', 'success');
      inputQuickExpCat.value = '';
      await fetchExpenseCategories();
      if (res.data && res.data.id) {
        expCategory.value = String(res.data.id);
      }
    } catch (err) {
      showToast(err.message);
    }
  });

  // 快速建立入帳分類
  btnQuickCreateIncCat.addEventListener('click', async () => {
    const name = inputQuickIncCat.value.trim();
    if (!name) {
      showToast('請輸入入帳分類名稱');
      return;
    }
    try {
      const res = await apiRequest('/api/income-categories', {
        method: 'POST',
        body: { name }
      });
      showToast(res.message || '入帳分類建立成功', 'success');
      inputQuickIncCat.value = '';
      await fetchIncomeCategories();
      if (res.data && res.data.id) {
        incCategory.value = String(res.data.id);
      }
    } catch (err) {
      showToast(err.message);
    }
  });

  // 載入當前分頁歷史記錄
  async function fetchRecordsList() {
    recordsList.innerHTML = '<div class="loading-state">載入明細中...</div>';
    const endpoint = recordsActiveTab === 'expense' ? '/api/expenses' : '/api/incomes';

    try {
      const res = await apiRequest(endpoint);
      const items = Array.isArray(res.data) ? res.data : [];
      cachedRecordsList = items;
      renderRecordsList();
    } catch (err) {
      recordsList.innerHTML = `<div class="loading-state error-text">${escapeHTML(err.message)}</div>`;
      showToast(err.message);
    }
  }

  function renderRecordsList() {
    if (cachedRecordsList.length === 0) {
      recordsList.innerHTML = '<div class="empty-state">目前尚無記錄</div>';
      return;
    }

    recordsList.innerHTML = '';
    cachedRecordsList.forEach(item => {
      const row = document.createElement('div');
      row.className = 'record-item';

      if (recordsActiveTab === 'expense') {
        const title = item.merchant || item.note || '花費項目';
        const sub = `${item.spent_on} · ${item.note || item.merchant || ''}`;
        row.innerHTML = `
          <div class="record-left">
            <div class="record-title">${escapeHTML(title)}</div>
            <div class="record-meta">${escapeHTML(sub)}</div>
          </div>
          <div class="record-amount amount-negative">- ${formatTWD(item.amount)}</div>
        `;
      } else {
        const title = item.source || item.note || '入帳項目';
        const sub = `${item.received_on} · ${item.note || item.source || ''}`;
        row.innerHTML = `
          <div class="record-left">
            <div class="record-title">${escapeHTML(title)}</div>
            <div class="record-meta">${escapeHTML(sub)}</div>
          </div>
          <div class="record-amount amount-positive">+ ${formatTWD(item.amount)}</div>
        `;
      }

      recordsList.appendChild(row);
    });
  }

  // 儲存花費
  formExpense.addEventListener('submit', async (e) => {
    e.preventDefault();

    const spent_on = expSpentOn.value;
    const amount = parseFloat(expAmount.value);
    const category_id = parseInt(expCategory.value, 10);
    const account_id = parseInt(expAccount.value, 10);
    const merchant = expMerchant.value.trim() || null;
    const note = expNote.value.trim() || null;

    if (!spent_on) return showToast('請選擇消費日期');
    if (!amount || amount <= 0) return showToast('花費金額必須大於 0');
    if (!category_id) return showToast('請選擇花費分類');
    if (!account_id) return showToast('請選擇扣款帳戶');
    if (!merchant && !note) return showToast('消費商家與備註說明不可同時為空');

    // 客戶端嚴禁傳送 id, created_at, updated_at
    const payload = {
      spent_on,
      amount,
      currency: 'TWD',
      fx_rate_to_twd: 1.0,
      category_id,
      account_id,
      merchant,
      note
    };

    try {
      const res = await apiRequest('/api/expenses', {
        method: 'POST',
        body: payload
      });

      showToast(res.message || '花費建立成功', 'success');

      // 成功後把新列放在本月清單最上方
      if (res.data) {
        cachedRecordsList.unshift(res.data);
        renderRecordsList();
      }

      // 重設輸入表單
      expAmount.value = '';
      expMerchant.value = '';
      expNote.value = '';
    } catch (err) {
      showToast(err.message);
    }
  });

  // 儲存入帳
  formIncome.addEventListener('submit', async (e) => {
    e.preventDefault();

    const received_on = incReceivedOn.value;
    const amount = parseFloat(incAmount.value);
    const category_id = parseInt(incCategory.value, 10);
    const account_id = parseInt(incAccount.value, 10);
    const source = incSource.value.trim() || null;
    const note = incNote.value.trim() || null;

    if (!received_on) return showToast('請選擇入帳日期');
    if (!amount || amount <= 0) return showToast('入帳金額必須大於 0');
    if (!category_id) return showToast('請選擇入帳分類');
    if (!account_id) return showToast('請選擇收款帳戶');
    if (!source && !note) return showToast('資金來源與備註說明不可同時為空');

    // 客戶端嚴禁傳送 id, created_at, updated_at
    const payload = {
      received_on,
      amount,
      currency: 'TWD',
      fx_rate_to_twd: 1.0,
      category_id,
      account_id,
      source,
      note
    };

    try {
      const res = await apiRequest('/api/incomes', {
        method: 'POST',
        body: payload
      });

      showToast(res.message || '入帳建立成功', 'success');

      // 成功後把新列放在本月清單最上方
      if (res.data) {
        cachedRecordsList.unshift(res.data);
        renderRecordsList();
      }

      // 重設輸入表單
      incAmount.value = '';
      incSource.value = '';
      incNote.value = '';
    } catch (err) {
      showToast(err.message);
    }
  });

  // ==========================================
  // 4. 投資邏輯 (Investments View)
  // ==========================================
  const investmentsList = document.getElementById('investments-list');
  const btnFetchQuotes = document.getElementById('btn-fetch-quotes');
  const fetchStatusText = document.getElementById('fetch-status-text');

  async function loadInvestmentsData() {
    investmentsList.innerHTML = '<div class="loading-state">載入台股標的與持股中...</div>';

    try {
      const res = await apiRequest('/api/instruments');
      const allInstruments = Array.isArray(res.data) ? res.data : [];

      // 依規範列出 tw_stock 的名稱、代號
      const twStocks = allInstruments.filter(inst => inst.market === 'tw_stock');

      if (twStocks.length === 0) {
        investmentsList.innerHTML = '<div class="empty-state">目前尚無台股投資標的</div>';
        return;
      }

      // 對每一筆查詢 holding 與 quote
      const details = await Promise.all(twStocks.map(async (inst) => {
        let holdingQty = 0;
        let quoteText = '還沒有報價';

        // 1. 持有數量來自 GET /api/instruments/<id>/holding
        try {
          const holdRes = await apiRequest(`/api/instruments/${inst.id}/holding`);
          if (holdRes.data && holdRes.data.quantity !== undefined) {
            holdingQty = holdRes.data.quantity;
          }
        } catch (_) {
          holdingQty = 0;
        }

        // 2. 最新報價來自 GET /api/instruments/<id>/quote
        try {
          const quoteRes = await apiRequest(`/api/instruments/${inst.id}/quote`);
          if (quoteRes.data && (quoteRes.data.price !== undefined || quoteRes.data.quote !== undefined)) {
            const price = quoteRes.data.price ?? quoteRes.data.quote;
            quoteText = formatTWD(price);
          }
        } catch (_) {
          quoteText = '還沒有報價';
        }

        return {
          id: inst.id,
          name: inst.name,
          symbol: inst.symbol,
          quantity: holdingQty,
          quoteText
        };
      }));

      // 渲染台股標的清單
      investmentsList.innerHTML = '';
      details.forEach(item => {
        const card = document.createElement('div');
        card.className = 'instrument-card';
        card.innerHTML = `
          <div class="instrument-info">
            <div class="instrument-name">${escapeHTML(item.name)}</div>
            <div class="instrument-symbol">${escapeHTML(item.symbol)} · 台股</div>
          </div>
          <div class="instrument-numbers">
            <div class="instrument-quote">${escapeHTML(item.quoteText)}</div>
            <div class="instrument-holding">持有 ${formatQuantity(item.quantity)} 股</div>
          </div>
        `;
        investmentsList.appendChild(card);
      });
    } catch (err) {
      investmentsList.innerHTML = `<div class="loading-state error-text">${escapeHTML(err.message)}</div>`;
      showToast(err.message);
    }
  }

  // 抓取台股報價按鈕
  btnFetchQuotes.addEventListener('click', async () => {
    btnFetchQuotes.disabled = true;
    btnFetchQuotes.textContent = '抓取中...';
    fetchStatusText.classList.add('hidden');

    try {
      // POST /api/tw-stock-quotes/fetch
      const res = await apiRequest('/api/tw-stock-quotes/fetch', {
        method: 'POST'
      });

      // missing 與 skipped 用一句人話帶過
      let summaryText = '台股報價已更新完成';
      if (res.data) {
        const skipped = res.data.skipped ?? 0;
        const missing = res.data.missing ?? 0;
        if (skipped > 0 || missing > 0) {
          summaryText = `報價更新完成（部分標的已略過或目前尚無開盤報價）`;
        }
      }

      fetchStatusText.textContent = summaryText;
      fetchStatusText.classList.remove('hidden');
      showToast(summaryText, 'success');

      // 完成後重讀
      await loadInvestmentsData();
    } catch (err) {
      // 失敗時畫面只顯示 message
      showToast(err.message);
      fetchStatusText.textContent = err.message;
      fetchStatusText.classList.remove('hidden');
    } finally {
      btnFetchQuotes.disabled = false;
      btnFetchQuotes.textContent = '抓取台股報價';
    }
  });

  // ==========================================
  // 5. 發票邏輯 (Invoices View - 只讀)
  // ==========================================
  const invoicesList = document.getElementById('invoices-list');

  async function loadInvoicesData() {
    invoicesList.innerHTML = '<div class="loading-state">載入發票清單中...</div>';

    try {
      // GET /api/invoices
      const res = await apiRequest('/api/invoices');
      const invoices = Array.isArray(res.data) ? res.data : [];

      if (invoices.length === 0) {
        invoicesList.innerHTML = '<div class="empty-state">目前無發票紀錄</div>';
        return;
      }

      invoicesList.innerHTML = '';
      invoices.forEach(inv => {
        const meta = getPrizeStatusMeta(inv.prize_status);
        const card = document.createElement('div');
        card.className = 'invoice-card';
        card.innerHTML = `
          <div class="invoice-left">
            <div class="invoice-number">${escapeHTML(inv.number)}</div>
            <div class="invoice-date">${escapeHTML(inv.issued_on || '')} · ${escapeHTML(inv.period_key || '')}</div>
          </div>
          <div class="invoice-right">
            <div class="invoice-amount">${formatTWD(inv.amount)}</div>
            <span class="invoice-status-badge ${meta.cls}">${escapeHTML(meta.label)}</span>
          </div>
        `;
        invoicesList.appendChild(card);
      });
    } catch (err) {
      invoicesList.innerHTML = `<div class="loading-state error-text">${escapeHTML(err.message)}</div>`;
      showToast(err.message);
    }
  }

  // ==========================================
  // XSS 防禦小工具
  // ==========================================
  function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ==========================================
  // 應用程式初始化
  // ==========================================
  async function initApp() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) {
      switchView('connection');
      return;
    }

    try {
      const parsed = JSON.parse(saved);
      if (parsed && parsed.apiBaseUrl) {
        apiBaseUrl = parsed.apiBaseUrl;
        inputApiUrl.value = apiBaseUrl;

        // 已存過的連線，下次打開先重查這一次 health check
        const res = await apiRequest('/api/health');
        if (res.code === 200 && res.data && res.data.status === 'ok') {
          switchView('home');
        } else {
          switchView('connection');
          showToast(res.message || '目前連不上記帳服務');
        }
      } else {
        switchView('connection');
      }
    } catch (err) {
      switchView('connection');
      showToast(err.message || '目前連不上記帳服務');
    }
  }

  // 啟動應用
  initApp();
})();
