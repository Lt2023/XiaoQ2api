"use strict";

const ADMIN_KEY_STORAGE = "xiaoq-console-admin-key";
function loadSavedAdminKey() {
  try {
    return localStorage.getItem(ADMIN_KEY_STORAGE) || "";
  } catch {
    return "";
  }
}
function saveSavedAdminKey(value) {
  try {
    localStorage.setItem(ADMIN_KEY_STORAGE, value);
    return true;
  } catch {
    return false;
  }
}
function clearSavedAdminKey() {
  try {
    localStorage.removeItem(ADMIN_KEY_STORAGE);
  } catch {}
}
const state = {
  adminKey: loadSavedAdminKey(),
  overview: null,
  page: "dashboard",
  connected: false,
  playgroundMessages: [],
  playgroundBusy: false,
};
const pageContent = document.querySelector("#page-content");
const loginDialog = document.querySelector("#login-dialog");
const editorDialog = document.querySelector("#editor-dialog");
const pages = {
  dashboard: {
    title: "控制台",
    eyebrow: "OVERVIEW",
    description: "每一次请求，都井然有序。",
  },
  playground: {
    title: "游乐场",
    eyebrow: "PLAYGROUND",
    description: "在线发送问题，直接测试当前接口对话。",
  },
  accounts: {
    title: "账号管理",
    eyebrow: "ACCOUNTS",
    description: "管理 NapCat 连接，让你的服务始终就绪。",
  },
  keys: {
    title: "API Key 管理",
    eyebrow: "API KEYS",
    description: "为每一个应用，分配独立的访问凭证。",
  },
  logs: {
    title: "日志管理",
    eyebrow: "ACTIVITY",
    description: "查看接口请求状态与管理操作记录。",
  },
  settings: {
    title: "系统设置",
    eyebrow: "PREFERENCES",
    description: "按你的方式，配置XiaoQ 接口。",
  },
};

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
}
function icon(name) {
  return `<span class="icon icon-${name}" aria-hidden="true"></span>`;
}
function pill(label, color = "") {
  return `<span class="pill ${color}">${escapeHtml(label)}</span>`;
}
function number(value) {
  return new Intl.NumberFormat("zh-CN").format(value ?? 0);
}
function formatDate(value, withTime = false) {
  return new Date(value).toLocaleString(
    "zh-CN",
    withTime
      ? { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }
      : { year: "numeric", month: "2-digit", day: "2-digit" },
  );
}
let toastTimer;
function notify(message, isError = false) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 4500);
}
async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(`/admin/api${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${state.adminKey}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      state.connected = false;
      state.adminKey = "";
      clearSavedAdminKey();
      updateConnection();
      if (!loginDialog.open) loginDialog.showModal();
    }
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : "输入有误，请检查字段后重试";
    const error = new Error(
      response.status >= 500
        ? data.detail || "服务暂时不可用，请稍后重试"
        : detail,
    );
    error.status = response.status;
    throw error;
  }
  return data;
}
function qqAvatarId(account) {
  const value = String(account?.qq_id ?? "").trim();
  return /^[1-9]\d{4,11}$/.test(value) ? value : "";
}
function avatarContent(account) {
  const label = String(account?.nickname || account?.name || "Q").trim();
  const fallback = escapeHtml(Array.from(label)[0] || "Q");
  const qqId = qqAvatarId(account);
  if (!qqId) return fallback;
  const src = `https://q.qlogo.cn/headimg_dl?dst_uin=${qqId}&spec=640&img_type=jpg`;
  return `<img class="qq-avatar-image" src="${src}" alt="" loading="lazy" referrerpolicy="no-referrer"><span class="qq-avatar-fallback" hidden>${fallback}</span>`;
}
function updateAccountAvatars() {
  const activeAccount = state.overview?.accounts?.find((account) => account.active);
  const content = avatarContent(activeAccount);
  ["#workspace-avatar", "#profile-avatar"].forEach((selector) => {
    const avatar = document.querySelector(selector);
    if (avatar) avatar.innerHTML = content;
  });
}
document.addEventListener("error", (event) => {
  const image = event.target;
  if (!(image instanceof HTMLImageElement) || !image.classList.contains("qq-avatar-image")) return;
  image.hidden = true;
  const fallback = image.nextElementSibling;
  if (fallback) fallback.hidden = false;
}, true);
function updateConnection() {
  const badge = document.querySelector("#connection-status");
  badge.classList.toggle("muted", !state.connected);
  badge.innerHTML = `<span class="tiny-dot"></span>${state.connected ? "服务已连接" : "未连接"}`;
  document.querySelector("#session-label").textContent = state.adminKey
    ? "管理员"
    : "管理员登录";
  document.querySelector("#session-button").title = state.adminKey
    ? "退出登录"
    : "登录控制台";
}
async function refresh(render = true) {
  const key = state.adminKey;
  const data = await request("/overview");
  if (key !== state.adminKey) return;
  state.overview = data;
  state.connected = true;
  updateConnection();
  updateAccountAvatars();
  document.querySelector("#last-updated").textContent =
    `更新于 ${formatDate(new Date(), true)}`;
  if (render) renderPage();
}
function emptyState(title, text, name = "terminal") {
  return `<div class="empty-state"><div class="empty-icon">${icon(name)}</div><h3>${title}</h3><p>${text}</p></div>`;
}
function statsCard(title, value, foot, name, unit = "", blue = false) {
  return `<div class="stat-card"><div class="stat-top"><span>${title}</span><span class="stat-icon ${blue ? "blue" : ""}">${icon(name)}</span></div><div class="stat-value">${value}<small>${unit}</small></div><div class="stat-foot">${foot}</div></div>`;
}
function dashboard() {
  const data = state.overview;
  const total = data?.total ?? 0;
  const activeKeys = data?.keys.filter((key) => key.enabled).length ?? 0;
  const account = data?.accounts.find((item) => item.active);
  const success = total
    ? `${(((total - data.errors) / total) * 100).toFixed(1)}%`
    : "—";
  const traffic = data?.traffic ?? Array(24).fill(0);
  const maximum = Math.max(4, ...traffic);
  const chartBars = traffic
    .map(
      (count, index) =>
        `<div class="chart-bar" style="height:${Math.max(1, (count / maximum) * 100)}%" title="${23 - index} 分钟前：${count} 次请求"></div>`,
    )
    .join("");
  const rows = data?.events.slice(0, 6) ?? [];
  const uptime = data
    ? `${Math.floor(data.uptime_seconds / 3600)} 小时 ${Math.floor((data.uptime_seconds % 3600) / 60)} 分钟`
    : "—";
  return `<div class="stats-grid">
    ${statsCard("累计请求", data ? number(total) : "—", "本次服务启动以来", "terminal", "次", true)}
    ${statsCard("请求成功率", data ? success : "—", total ? `<span class="green">${number(total - data.errors)} 次成功</span> / ${number(total)} 次请求` : "等待第一条请求", "check")}
    ${statsCard("账号连接配置", data ? number(data.accounts.length) : "—", account ? '<span class="green">1 个当前账号</span>手动切换' : "尚未连接工作空间", "users", "个")}
    ${statsCard("可用 API Key", data ? number(activeKeys) : "—", data ? `共 ${data.keys.length} 个访问凭证` : "独立管理应用访问", "key", "个")}
  </div>
  <div class="overview-grid"><section class="panel"><div class="panel-header"><div><h2>请求趋势</h2><p class="panel-subtitle">最近 24 分钟 · 每分钟请求数</p></div><span class="chart-legend"><i></i> API 请求</span></div><div class="chart-container" role="img" aria-label="最近24分钟请求数量：${traffic.join(",")}"><div class="chart-ticks"><span>${maximum}</span><span>${Math.round(maximum * 0.75)}</span><span>${Math.round(maximum / 2)}</span><span>${Math.round(maximum / 4)}</span><span>0</span></div><div class="chart-bars">${chartBars}</div>${traffic.every((value) => value === 0) ? '<div class="chart-empty"><strong>还没有请求记录</strong><span>发起一次 API 调用，数据会显示在这里</span></div>' : ""}</div><div class="chart-labels"><span>23 分钟前</span><span>16 分钟前</span><span>8 分钟前</span><span>现在</span></div></section>
  <section class="panel"><div class="panel-header"><h2>服务概览</h2>${pill(state.connected ? "运行中" : "待连接", state.connected ? "green" : "")}</div><div class="service-body"><div class="service-row"><span>模型</span><code>tenxun-hunyuan-3</code></div><div class="service-row"><span>工具调用</span>${pill(data?.settings.fc_mode === "auto" ? "自动模式" : "兼容调用 · XYML", "blue")}</div><div class="service-row"><span>当前账号</span><span>${escapeHtml(account?.name || "—")}</span></div><div class="service-row"><span>运行时间</span><span>${uptime}</span></div><div class="service-flow"><span>客户端</span>${icon("arrow")}<strong>工具兼容</strong>${icon("arrow")}<span>NapCat</span>${icon("arrow")}<span>XiaoQ</span></div></div></section></div>
  <div class="endpoint-banner">${icon("terminal")}<div><strong>你的 OpenAI 兼容接口</strong><code>${escapeHtml(location.origin)}/v1</code></div><button class="text-button" data-action="copy-endpoint">${icon("copy")}复制地址</button></div>
  <section class="panel table-panel"><div class="panel-header"><div><h2>最近请求</h2><p class="panel-subtitle">实时掌握接口状态，不记录请求正文与密钥</p></div><span class="pill">最近 ${rows.length} 条</span></div>${rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>时间</th><th>请求路径</th><th>状态</th><th>响应头耗时</th></tr></thead><tbody>${rows.map((event) => `<tr><td>${formatDate(event.time, true)}</td><td><code>${escapeHtml(event.method)} ${escapeHtml(event.path)}</code></td><td>${pill(event.status, event.status < 400 ? "green" : "red")}</td><td>${number(event.duration_ms)} ms</td></tr>`).join("")}</tbody></table></div>` : emptyState("等待第一条请求", "连接你的客户端，开始与XiaoQ 对话。")}<div class="table-note">数据仅统计当前进程；SSE 耗时不包含完整流传输，HTTP 成功状态不代表上游推理成功。</div></section>`;
}
function accountsPage() {
  const accounts = state.overview?.accounts ?? [];
  return `<div class="notice">${icon("users")}<span>每个账号对应一个 NapCat HTTP 连接。点击“测试”会读取 NapCat 登录信息并同步 QQ 头像；切换账号后顶部头像跟随当前连接。</span></div><div class="account-grid">${accounts.map((account) => `<article class="panel account-card ${account.active ? "is-active" : ""}"><div class="account-heading"><span class="account-avatar qq-avatar-frame">${avatarContent(account)}</span><div><h3>${escapeHtml(account.name)}</h3><small>NapCat · HTTP API</small></div>${pill(account.active ? "当前使用" : "备用账号", account.active ? "blue" : "")}</div><div class="account-detail"><span>服务地址</span><code>${escapeHtml(account.base_url)}</code></div><div class="account-detail"><span>QQ 号码</span><span>${account.qq_id ? escapeHtml(account.qq_id) : "尚未获取"}</span></div><div class="account-detail"><span>访问 Token</span><span>${account.has_token ? "已配置 · 隐藏保存" : "未配置"}</span></div><div class="account-detail"><span>添加时间</span><span>${formatDate(account.created_at)}</span></div><div class="account-actions"><button class="button small" data-action="test-account" data-id="${account.id}">测试</button><button class="button small" data-action="edit-account" data-id="${account.id}">编辑</button>${!account.active ? `<button class="text-button" data-action="activate-account" data-id="${account.id}">设为当前</button>` : ""}<button class="icon-button delete-action" data-action="delete-account" data-id="${account.id}" aria-label="删除 ${escapeHtml(account.name)}">${icon("delete")}</button></div></article>`).join("")}</div>${!accounts.length ? emptyState("还没有账号", "添加 NapCat 连接后即可开始使用。", "users") : ""}`;
}
function playgroundPage() {
  const messages = state.playgroundMessages.map((message) => {
    const isUser = message.role === "user";
    const role = isUser ? "你" : "XiaoQ";
    const kind = isUser ? "user" : "assistant";
    return `<div class="playground-turn ${kind}"><span class="playground-role">${role}</span><article class="playground-message ${kind}"><p>${escapeHtml(message.content)}</p></article></div>`;
  }).join("");
  const empty = `<div class="playground-empty"><span class="empty-icon">${icon("playground")}</span><h2>开始测试对话</h2><p>发送一个问题，验证当前 API 和 NapCat 连接是否正常。</p></div>`;
  const pending = state.playgroundBusy ? `<div class="playground-turn assistant"><span class="playground-role">XiaoQ</span><article class="playground-message assistant"><p class="playground-pending">正在等待回复…</p></article></div>` : "";
  return `<section class="panel playground-panel"><header class="playground-header"><div><h2>在线测试对话</h2><p>请求会发送到当前服务的 <code>/v1/chat/completions</code> 接口。</p></div>${pill(state.connected ? "服务已连接" : "等待连接", state.connected ? "green" : "")}</header><div id="playground-messages" class="playground-messages" aria-live="polite">${messages || empty}${pending}</div><form id="playground-form" class="playground-composer"><textarea id="playground-input" name="message" rows="2" maxlength="12000" placeholder="输入你的问题…" aria-label="输入问题" ${state.playgroundBusy ? "disabled" : ""} required></textarea><div class="playground-composer-footer"><span class="playground-model-label" aria-label="当前模型">tenxun-hunyuan-3<span class="playground-chevron" aria-hidden="true"></span></span><button class="playground-send" type="submit" aria-label="发送" title="发送" ${state.playgroundBusy ? "disabled" : ""}><span class="icon icon-send" aria-hidden="true"></span></button></div></form></section>`;
}
function keysPage() {
  const keys = state.overview?.keys ?? [];
  return `<div class="notice">${icon("key")}<span>新密钥仅在创建时展示一次，服务器仅保存哈希。API Key 用于客户端调用，管理员登录仍使用 config.env 中的 api_key。</span></div><section class="panel table-panel"><div class="panel-header"><div><h2>访问凭证</h2><p class="panel-subtitle">停用或删除后立即拒绝新的 API 请求</p></div>${pill(`${keys.length} 个密钥`)}</div>${keys.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>名称</th><th>密钥</th><th>创建日期</th><th>状态</th><th>操作</th></tr></thead><tbody>${keys.map((key) => `<tr><td class="name-cell">${escapeHtml(key.name)}</td><td><code>${escapeHtml(key.preview)}</code></td><td>${formatDate(key.created_at)}</td><td>${pill(key.enabled ? "使用中" : "已停用", key.enabled ? "green" : "")}</td><td><div class="row-actions"><button class="text-button" data-action="toggle-key" data-id="${key.id}">${key.enabled ? "停用" : "启用"}</button><button class="icon-button" data-action="delete-key" data-id="${key.id}" aria-label="删除 ${escapeHtml(key.name)}">${icon("delete")}</button></div></td></tr>`).join("")}</tbody></table></div>` : emptyState("为应用创建第一把密钥", "为不同客户端分配不同的 API Key，方便独立管理。", "key")}<div class="table-note">已有调用不受停用影响；原有密钥停用不会影响管理控制台登录。</div></section>`;
}
function settingsPage() {
  const settings = state.overview?.settings;
  if (!settings) return emptyState("请先登录控制台", "验证管理员密钥后即可修改配置。", "settings");
  return `<div class="settings-grid"><form id="settings-form" class="panel settings-form"><h2 class="form-section-title">接口设置</h2><p class="form-section-description">配置会保存到本地并即时生效，无需重新启动服务。</p><div class="field"><label for="fc-mode">工具调用模式</label><select id="fc-mode" name="fc_mode"><option value="force_prompt" ${settings.fc_mode === "force_prompt" ? "selected" : ""}>提示词兼容模式</option><option value="auto" ${settings.fc_mode === "auto" ? "selected" : ""}>自动模式</option></select><p class="field-help">请求中提供工具定义时启用兼容解析；普通聊天会正常回复。</p></div><div class="switch-row"><div><label for="retry-enabled">工具解析失败重试</label><p>遇到可恢复的格式错误时，自动尝试恢复。</p></div><input class="switch" id="retry-enabled" name="enable_fc_error_retry" type="checkbox" ${settings.enable_fc_error_retry ? "checked" : ""}></div><div class="settings-actions"><span>设置变更会等待当前请求结束</span><button class="button primary" type="submit">保存设置 ${icon("check")}</button></div></form><aside class="panel settings-aside"><h3>配置说明</h3><p><strong>连接配置</strong><br>在「账号管理」中修改 NapCat 地址与 Token。</p><p><strong>管理员凭证</strong><br>继续使用项目 <code>config.env</code> 中的 <code>api_key</code>。</p><p><strong>配置优先级</strong><br>本机控制台设置保存在独立文件，不覆盖原始配置。</p><p><strong>数据存储</strong><br>连接 Token 仅用于上游连接，会保存在本机；请保护配置文件。</p></aside></div>`;
}

function activityPanel(entries = []) {
  const recent = entries.slice(0, 8);
  const names = {account_added:"账号已添加",account_updated:"账号已更新",account_activated:"连接已切换",account_deleted:"账号已删除",key_created:"密钥已创建",key_updated:"密钥状态已更新",key_deleted:"密钥已删除",settings_updated:"接口设置已更新",theme_changed:"外观已切换"};
  return `<section class="panel table-panel activity-panel"><div class="panel-header"><div><h2>操作日志</h2><p class="panel-subtitle">账号、密钥、设置和主题变更</p></div><span class="pill">最近 ${recent.length} 条</span></div>${recent.length ? `<div class="activity-list">${recent.map(entry => `<article class="activity-row"><span class="activity-mark">${icon(entry.action === "theme_changed" ? "sun" : "check")}</span><div class="activity-copy"><strong>${escapeHtml(names[entry.action] || "系统事件")}</strong><p>${escapeHtml(entry.detail)}</p></div><time datetime="${escapeHtml(entry.time)}">${formatDate(entry.time, true)}</time></article>`).join("")}</div>` : emptyState("暂无操作记录", "主题与配置变更会显示在这里。", "terminal")}<div class="table-note">日志仅保留操作摘要，不记录密钥值或请求正文。</div></section>`;
}

function logsPage() {
  const requests = (state.overview?.events || []).map((entry) => ({
    time: entry.time,
    type: "request",
    detail: `${entry.method} ${entry.path}`,
    status: entry.status,
    duration: entry.duration_ms,
  }));
  const actions = (state.overview?.activity || []).map((entry) => ({
    time: entry.time,
    type: "activity",
    detail: entry.detail,
    action: entry.action,
  }));
  const filter = state.logFilter || "all";
  const rows = [...requests, ...actions]
    .filter((entry) => filter === "all" || entry.type === filter)
    .sort((left, right) => new Date(right.time) - new Date(left.time));
  return `<section class="panel table-panel log-manager"><div class="panel-header"><div><h2>运行与操作记录</h2><p class="panel-subtitle">仅记录请求元信息与配置变更，不采集密钥或消息内容</p></div><label class="log-filter-label" for="log-filter">显示<select id="log-filter"><option value="all" ${filter === "all" ? "selected" : ""}>全部记录</option><option value="request" ${filter === "request" ? "selected" : ""}>API 请求</option><option value="activity" ${filter === "activity" ? "selected" : ""}>管理操作</option></select></label></div>${rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>时间</th><th>类别</th><th>摘要</th><th>结果</th></tr></thead><tbody>${rows.map((entry) => `<tr><td>${formatDate(entry.time, true)}</td><td>${pill(entry.type === "request" ? "API 请求" : "管理操作", entry.type === "request" ? "blue" : "")}</td><td class="name-cell">${escapeHtml(entry.detail)}</td><td>${entry.type === "request" ? `${pill(entry.status, entry.status < 400 ? "green" : "red")}${entry.duration === undefined ? "" : ` <span class="log-duration">${number(entry.duration)} ms</span>`}` : "—"}</td></tr>`).join("")}</tbody></table></div>` : emptyState("暂无匹配记录", "新请求与配置操作出现后会自动记入日志。", "terminal")}<div class="table-note">接口请求日志仅保留当前进程最近 100 条；管理操作日志保存在本机。</div></section>`;
}

function renderPage() {
  const page = pages[state.page];
  document.querySelector("#breadcrumb").textContent = page.title;
  document.querySelector("#page-title").textContent = page.title;
  document.querySelector("#page-eyebrow").textContent = page.eyebrow;
  document.querySelector("#page-description").textContent = page.description;
  document.querySelectorAll("[data-page]").forEach((link) => {
    const active = link.dataset.page === state.page;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const primary =
    state.page === "accounts"
      ? `<button class="button primary" data-action="add-account">${icon("add")}添加账号</button>`
      : state.page === "keys"
        ? `<button class="button primary" data-action="add-key">${icon("add")}创建 API Key</button>`
        : state.page === "dashboard"
          ? `<a class="button primary" href="#keys">${icon("add")}创建 API Key</a>`
          : "";
  document.querySelector("#page-actions").innerHTML =
    `<button class="button" data-action="refresh">${icon("refresh")}刷新</button>${primary}`;
  pageContent.innerHTML = {
    dashboard,
    playground: playgroundPage,
    accounts: accountsPage,
    keys: keysPage,
    logs: logsPage,
    settings: settingsPage,
  }[state.page]();
  if (state.page === "dashboard") {
    pageContent.insertAdjacentHTML("beforeend", activityPanel(state.overview?.activity || []));
  }
  if (state.page === "playground") {
    const conversation = pageContent.querySelector("#playground-messages");
    if (conversation) conversation.scrollTop = conversation.scrollHeight;
  }
  pageContent.classList.remove("page-enter");
  void pageContent.offsetWidth;
  requestAnimationFrame(() => pageContent.classList.add("page-enter"));
}
function navigate() {
  const page = location.hash.slice(1) || "dashboard";
  state.page = pages[page] ? page : "dashboard";
  renderPage();
  window.scrollTo({ top: 0 });
}
function openEditor(title, html) {
  document.querySelector("#editor-title").textContent = title;
  document.querySelector("#editor-body").innerHTML = html;
  if (!editorDialog.open) editorDialog.showModal();
}
function confirmAction(title, description, action) {
  openEditor(
    title,
    `<p class="dialog-intro">${escapeHtml(description)}</p><div class="form-actions"><button class="button" data-close>取消</button><button id="confirm-action" class="button danger">确认</button></div>`,
  );
  document.querySelector("#confirm-action").onclick = async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await action();
      editorDialog.close();
      if (state.adminKey) await refresh();
    } catch (error) {
      notify(error.message, true);
    } finally {
      button.disabled = false;
    }
  };
}
function accountEditor(account) {
  openEditor(
    account ? "编辑账号" : "添加 NapCat 账号",
    `<form id="account-form"><div class="field"><label for="account-name">账号名称</label><input id="account-name" name="name" value="${escapeHtml(account?.name || "")}" placeholder="例如：我的XiaoQ" maxlength="60" required></div><div class="field"><label for="account-url">NapCat HTTP 地址</label><input id="account-url" name="base_url" type="url" value="${escapeHtml(account?.base_url || "")}" placeholder="http://127.0.0.1:3000" required></div><div class="field"><label for="account-token">访问 Token</label><input id="account-token" name="token" type="password" autocomplete="new-password" placeholder="${account ? "留空则保留原 Token" : "填写 NapCat 配置中的 Token"}"><p class="field-help">${account ? "Token 不会回显；更换账号后需重新测试连接。" : "添加后会自动测试连接并同步 QQ 头像。"}</p></div><div class="form-actions"><button type="button" class="button" data-close>取消</button><button type="submit" class="button primary">${account ? "保存修改" : "添加并测试"}</button></div></form>`,
  );
  document.querySelector("#account-form").onsubmit = async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const body = Object.fromEntries(new FormData(event.target));
      const saved = await request(account ? `/accounts/${account.id}` : "/accounts", {
        method: account ? "PUT" : "POST",
        body,
      });
      editorDialog.close();
      if (!account) {
        let testResult;
        try {
          testResult = await request(`/accounts/${saved.id}/test`, { method: "POST" });
        } catch (testError) {
          await refresh();
          notify(`账号已添加，但连接测试失败：${testError.message}`, true);
          return;
        }
        let activationError = null;
        if (testResult.user_id) {
          try {
            await request(`/accounts/${saved.id}/activate`, { method: "POST" });
          } catch (error) {
            activationError = error;
          }
        }
        await refresh();
        if (!testResult.user_id) {
          notify("账号已添加，连接测试成功但未获取到有效 QQ 号，头像暂未更新", true);
        } else if (activationError) {
          notify(`账号已添加，头像已同步但切换当前账号失败：${activationError.message}`, true);
        } else {
          notify("账号已添加、测试通过并设为当前，头像已同步");
        }
        return;
      }
      await refresh();
      notify("账号配置已保存");
    } catch (error) {
      notify(error.message, true);
    } finally {
      button.disabled = false;
    }
  };
}
function keyEditor() {
  openEditor(
    "创建 API Key",
    `<form id="key-form"><p class="dialog-intro">给密钥起一个易于识别的名称，例如客户端或应用名称。</p><label for="key-name">密钥名称</label><input id="key-name" name="name" placeholder="例如：Cherry Studio" maxlength="60" required><div class="form-actions"><button type="button" class="button" data-close>取消</button><button type="submit" class="button primary">创建密钥</button></div></form>`,
  );
  document.querySelector("#key-form").onsubmit = async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const data = await request("/keys", {
        method: "POST",
        body: Object.fromEntries(new FormData(event.target)),
      });
      openEditor(
        "密钥已创建",
        '<p class="dialog-intro">请立即复制并妥善保存。关闭后将无法再次查看完整密钥。</p><div id="new-secret" class="secret-box"></div><div class="form-actions"><button class="button" data-close>已保存，关闭</button><button class="button primary" id="copy-secret">复制密钥</button></div>',
      );
      document.querySelector("#new-secret").textContent = data.secret;
      document.querySelector("#copy-secret").onclick = () =>
        copyText(data.secret);
      await refresh();
    } catch (error) {
      notify(error.message, true);
    } finally {
      button.disabled = false;
    }
  };
}
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    notify("已复制到剪贴板");
  } catch {
    notify("当前浏览器未开放剪贴板，请手动选择复制", true);
  }
}
const actions = {
  refresh: async () => {
    if (
      state.page === "settings" &&
      !window.confirm("刷新将放弃尚未保存的设置，是否继续？")
    )
      return;
    await refresh();
    notify("数据已更新");
  },
  "copy-endpoint": () => copyText(`${location.origin}/v1`),
  "add-account": () => accountEditor(),
  "edit-account": (id) =>
    accountEditor(state.overview.accounts.find((account) => account.id === id)),
  "test-account": async (id) => {
    const result = await request(`/accounts/${id}/test`, { method: "POST" });
    await refresh();
    notify(result.user_id ? `连接成功 · 已同步 QQ ${result.user_id}` : "连接成功 · NapCat 未返回有效 QQ 号");
  },
  "activate-account": (id) =>
    confirmAction(
      "切换当前账号？",
      "新的请求将使用这个 NapCat 连接。正在处理的请求会先完成。",
      async () => {
        await request(`/accounts/${id}/activate`, { method: "POST" });
        notify("当前账号已切换");
      },
    ),
  "delete-account": (id) =>
    confirmAction(
      "删除账号？",
      "仅删除本地连接配置，不会注销 QQ 或删除 NapCat 数据。",
      async () => {
        await request(`/accounts/${id}`, { method: "DELETE" });
        notify("账号已删除");
      },
    ),
  "add-key": () => keyEditor(),
  "toggle-key": async (id) => {
    const key = state.overview.keys.find((item) => item.id === id);
    await request(`/keys/${id}`, {
      method: "PATCH",
      body: { enabled: !key.enabled },
    });
    await refresh();
    notify(key.enabled ? "密钥已停用" : "密钥已启用");
  },
  "delete-key": (id) =>
    confirmAction(
      "删除 API Key？",
      "使用该密钥的客户端将无法发起新的请求，此操作不能撤销。",
      async () => {
        await request(`/keys/${id}`, { method: "DELETE" });
        notify("密钥已删除");
      },
    ),
};
document.addEventListener("click", async (event) => {
  if (event.target.closest("[data-close]")) {
    editorDialog.close();
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  if (!state.adminKey) {
    loginDialog.showModal();
    return;
  }
  button.disabled = true;
  try {
    await actions[button.dataset.action]?.(button.dataset.id);
  } catch (error) {
    notify(error.message, true);
    updateConnection();
  } finally {
    button.disabled = false;
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id !== "log-filter") return;
  state.logFilter = event.target.value;
  renderPage();
});
document.addEventListener("keydown", (event) => {
  if (event.target.id !== "playground-input" || event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  event.target.form.requestSubmit();
});
document.addEventListener("submit", async (event) => {
  if (event.target.id === "playground-form") {
    event.preventDefault();
    if (!state.adminKey) {
      loginDialog.showModal();
      return;
    }
    if (state.playgroundBusy) return;
    const message = String(new FormData(event.target).get("message") || "").trim();
    if (!message) return;
    state.playgroundMessages.push({ role: "user", content: message });
    state.playgroundBusy = true;
    renderPage();
    let failure = null;
    try {
      const response = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${state.adminKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: "tenxun-hunyuan-3",
          messages: state.playgroundMessages.slice(-24),
          stream: false,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "对话请求失败，请检查 API 与账号连接");
      }
      const reply = data?.choices?.[0]?.message?.content;
      if (typeof reply !== "string") throw new Error("接口没有返回文本回复");
      state.playgroundMessages.push({ role: "assistant", content: reply });
    } catch (error) {
      failure = error.message;
    } finally {
      state.playgroundBusy = false;
      try {
        await refresh();
      } catch {
        renderPage();
      }
      if (failure) notify(failure, true);
    }
    return;
  }
  if (event.target.id !== "settings-form") return;
  event.preventDefault();
  const button = event.target.querySelector("[type=submit]");
  button.disabled = true;
  try {
    const form = new FormData(event.target);
    await request("/settings", {
      method: "PUT",
      body: {
        fc_mode: form.get("fc_mode"),
        enable_fc_error_retry: form.has("enable_fc_error_retry"),
      },
    });
    await refresh();
    notify("设置已保存并生效");
  } catch (error) {
    notify(error.message, true);
  } finally {
    button.disabled = false;
  }
});
document
  .querySelector("#login-form")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.target.querySelector("[type=submit]");
    button.disabled = true;
    state.adminKey = document.querySelector("#admin-key").value.trim();
    document.querySelector("#login-error").textContent = "";
    try {
      await refresh();
      const saved = saveSavedAdminKey(state.adminKey);
      document.querySelector("#admin-key").value = "";
      loginDialog.close();
      if (!saved) notify("\u767b\u5f55\u6210\u529f\uff0c\u4f46\u6d4f\u89c8\u5668\u672a\u80fd\u4fdd\u5b58\u767b\u5f55\u72b6\u6001", true);
    } catch (error) {
      state.adminKey = "";
      if (error.status === 401) clearSavedAdminKey();
      document.querySelector("#login-error").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
document.querySelector("#toggle-password").onclick = () => {
  const input = document.querySelector("#admin-key");
  input.type = input.type === "password" ? "text" : "password";
};
document.querySelector("#session-button").onclick = () => {
  if (!state.adminKey) {
    loginDialog.showModal();
    return;
  }
  confirmAction(
    "退出控制台？",
    "\u9000\u51fa\u540e\u4f1a\u5220\u9664\u6b64\u6d4f\u89c8\u5668\u4fdd\u5b58\u7684\u767b\u5f55\u72b6\u6001\uff0c\u670d\u52a1\u4f1a\u7ee7\u7eed\u8fd0\u884c\u3002",
    async () => {
      clearSavedAdminKey();
      state.adminKey = "";
      state.overview = null;
      state.connected = false;
      updateConnection();
      updateAccountAvatars();
      renderPage();
      loginDialog.showModal();
    },
  );
};
// Closing the secret dialog also releases its plaintext from the DOM and handlers.
editorDialog.addEventListener("close", () => {
  document.querySelector("#editor-body").replaceChildren();
});

function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  document.documentElement.style.colorScheme = selected;
  const button = document.querySelector("#theme-toggle");
  const dark = selected === "dark";
  button.setAttribute("aria-label", dark ? "切换浅色模式" : "切换深色模式");
  button.title = dark ? "切换浅色模式" : "切换深色模式";
  button.innerHTML = icon(dark ? "sun" : "moon");
}

let savedTheme = "light";
try {
  savedTheme = localStorage.getItem("xiaoq-console-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
} catch {}
applyTheme(savedTheme);
document.querySelector("#theme-toggle").addEventListener("click", async () => {
  const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(theme);
  try { localStorage.setItem("xiaoq-console-theme", theme); } catch {}
  if (state.adminKey) {
    try { await request("/activity", { method: "POST", body: { theme } }); await refresh(); }
    catch (error) { notify(error.message, true); }
  }
});

window.addEventListener("hashchange", navigate);
setInterval(async () => {
  if (
    !state.adminKey ||
    document.hidden ||
    editorDialog.open ||
    state.page !== "dashboard"
  )
    return;
  try {
    await refresh();
  } catch {
    state.connected = false;
    updateConnection();
  }
}, 15000);
navigate();
if (state.adminKey) {
  refresh().catch((error) => {
    if (error.status === 401) {
      state.adminKey = "";
      clearSavedAdminKey();
      updateConnection();
      if (!loginDialog.open) loginDialog.showModal();
      return;
    }
    notify(error.message, true);
  });
} else {
  loginDialog.showModal();
}
