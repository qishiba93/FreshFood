/**
 * frontend/js/app.js
 * 普通用户端交互控制核心 (全功能修复版)
 * 包含:
 * 1. 3D双门冰箱与门状态机
 * 2. 2D 食材卡片防溢出排版与自适应（彻底解决保质期/过期文字漏出底边问题）
 * 3. AI 厨房对话管家：支持长对话本地持久化、自然语言调度（买菜/删菜/入库冰箱/调整温区自适应并实时刷新界面）
 * 4. 彻底杜绝空白气泡：增强兜底指引机制，对无关问题提供清晰礼貌说明
 * 5. “营养菜谱”、“今日吃啥”、“收藏菜谱”、“社区菜谱”详细一点 0 秒直跳 AI 主厨页面
 * 6. 真实彻底清空 AI 记忆，杜绝上下文泄漏
 * 7. 双菜谱头部标签与按钮精准水平对齐，绝无单字折行
 */
import { Api } from './api.js';

// ==================== 1. 3D 冰箱与基础门状态 ====================
let isUpperDoorOpen = false;
let isLowerDoorOpen = false;
let fridge3D = null;
let fridgeItems = [];

function syncFridgeDoors() {
  fridge3D?.setDoors({ upper: isUpperDoorOpen, lower: isLowerDoorOpen });
  for (const [zone, open] of [['Upper', isUpperDoorOpen], ['Lower', isLowerDoorOpen]]) {
    const button = document.getElementById(`toggle${zone}3D`);
    button?.setAttribute('aria-pressed', String(open));
    button?.setAttribute('aria-label', `${open ? '关闭' : '开启'}${zone === 'Upper' ? '冷藏' : '冷冻'}门`);
    const closeButton = document.getElementById(`close${zone}DoorBtn`);
    if (closeButton && fridge3D) closeButton.textContent = open ? '关门' : '开门';
  }
  const statusEl = document.getElementById('fridgeDoorStatus');
  if (statusEl) {
    statusEl.textContent = `冷藏门已${isUpperDoorOpen ? '开启' : '关闭'} · 冷冻门已${isLowerDoorOpen ? '开启' : '关闭'}`;
  }
}

function toggleFridgeDoor(zone) {
  window.ensureAuth(() => {
    if (zone === 'upper') setUpperDoor(!isUpperDoorOpen);
    else setLowerDoor(!isLowerDoorOpen);
  });
}

function restoreFlatFridge() {
  fridge3D?.dispose();
  fridge3D = null;
  document.body.classList.remove('fridge-3d-ready');
  const sec = document.getElementById('fridge3DSection');
  if (sec) sec.hidden = true;
  document.getElementById('fridge3DCanvas')?.replaceChildren();
  const rStat = document.getElementById('fridgeRenderStatus');
  if (rStat) rStat.textContent = '已切换至标准视图';
  const cU = document.getElementById('closeUpperDoorBtn');
  const cL = document.getElementById('closeLowerDoorBtn');
  if (cU) cU.textContent = '关门 ✕';
  if (cL) cL.textContent = '关门 ✕';
}

async function initFridge3D() {
  window.lucide?.createIcons();
  document.querySelectorAll('#appContainer > aside nav button').forEach(button => {
    button.setAttribute('aria-label', button.textContent.trim());
    button.title = button.textContent.trim();
  });
  try {
    const { createFridge3D } = await import('./fridge-3d.js');
    document.body.classList.add('fridge-3d-ready');
    const sec = document.getElementById('fridge3DSection');
    if (sec) sec.hidden = false;
    fridge3D = createFridge3D({
      host: document.getElementById('fridge3DCanvas'),
      onDoorToggle: toggleFridgeDoor,
      onFoodSelect: item => window.ensureAuth(() => openFoodDetail(item)),
      onUnavailable: restoreFlatFridge,
    });
    fridge3D.setItems(fridgeItems);
    syncFridgeDoors();
  } catch (error) {
    console.warn('三维冰箱初始化失败，使用标准视图:', error);
    restoreFlatFridge();
  }
}

// ==================== 2. 全局状态缓存与多视图路由 ====================
let currentActiveItem = null;
let lastGeneratedRecipe = null;
let lastSpecialRecipe = null;
let lastTodayEatData = null;
let currentSpecialType = 'custom_health';

let allFavoritesCache = [];
let pendingBatchItems = [];
let pendingRecipeName = "";
let currentUser = null;
let currentAuthMode = 'login';
let recipeOptionsData = null;

let currentAiShelfRefrig = 3.0;
let currentAiShelfFreezer = 45.0;

let currentCommunityPosts = [];
let communityPage = 1;

let currentMainView = 'fridge';

// AI 对话历史记忆持久化键名
const CHAT_STORAGE_KEY = 'freshplate_chat_history_v2';
const CHAT_SUMMARY_KEY = 'freshplate_chat_summary_v2';
let chatHistory = [];
let currentChatRecipeContext = null;
let returnTargetScope = null;

// 小 AI 与当前页面的烹饪计时状态只保存在内存中，关闭网页即自动清空。
let miniAiHistory = [];
let miniAiBusy = false;
let miniAiStageQueue = [];
let cookingTimerState = null;
let cookingTimerInterval = null;
let miniAiDragMoved = false;

export function setUpperDoor(open) {
  isUpperDoorOpen = open;
  const leaf = document.getElementById("upperDoorLeaf");
  if (!leaf) return;
  if (open) leaf.classList.add("door-opened");
  else leaf.classList.remove("door-opened");
  syncFridgeDoors();
}

export function setLowerDoor(open) {
  isLowerDoorOpen = open;
  const leaf = document.getElementById("lowerDoorLeaf");
  if (!leaf) return;
  if (open) leaf.classList.add("door-opened");
  else leaf.classList.remove("door-opened");
  syncFridgeDoors();
}

window.setUpperDoor = setUpperDoor;
window.setLowerDoor = setLowerDoor;
window.openModal = (id) => document.getElementById(id)?.classList.remove('hidden');
window.closeModal = (id) => document.getElementById(id)?.classList.add('hidden');

function escapeMiniAiText(value) {
  return String(value || '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char])).replace(/\n/g, '<br>');
}

function setMiniAiVisible(visible) {
  const dock = document.getElementById('miniAiDock');
  if (dock) dock.classList.toggle('hidden', !visible);
}

function placeMiniAiPanel() {
  const dock = document.getElementById('miniAiDock');
  const panel = document.getElementById('miniAiPanel');
  if (!dock || !panel || panel.classList.contains('hidden') || dock.classList.contains('hidden')) return;

  const padding = 12;
  const gap = 10;
  const bubbleRect = dock.getBoundingClientRect();
  const panelWidth = panel.offsetWidth;
  const panelHeight = panel.offsetHeight;
  const maxLeft = Math.max(padding, window.innerWidth - panelWidth - padding);
  const left = Math.min(maxLeft, Math.max(padding, bubbleRect.right - panelWidth));
  const aboveTop = bubbleRect.top - panelHeight - gap;
  const belowTop = bubbleRect.bottom + gap;
  const maxTop = Math.max(padding, window.innerHeight - panelHeight - padding);
  const top = aboveTop >= padding
    ? aboveTop
    : Math.min(maxTop, Math.max(padding, belowTop));

  panel.style.left = `${left}px`;
  panel.style.top = `${top}px`;
  panel.style.right = 'auto';
  panel.style.bottom = 'auto';
}

function keepMiniAiDockInViewport() {
  const dock = document.getElementById('miniAiDock');
  if (!dock || dock.classList.contains('hidden')) return;
  if (dock.style.top) {
    const padding = 12;
    const height = dock.offsetHeight || 82;
    const maxTop = Math.max(padding, window.innerHeight - height - padding);
    const currentTop = dock.getBoundingClientRect().top;
    const top = Math.min(maxTop, Math.max(padding, currentTop));
    dock.style.top = `${top}px`;
    dock.style.bottom = 'auto';
  }
  placeMiniAiPanel();
}

function openMiniAiPanel() {
  const panel = document.getElementById('miniAiPanel');
  if (!panel) return;
  panel.classList.remove('hidden');
  window.requestAnimationFrame(placeMiniAiPanel);
  document.getElementById('miniAiInput')?.focus();
  const messages = document.getElementById('miniAiMessages');
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function appendMiniAiMessage(content, role = 'assistant', options = {}) {
  const messages = document.getElementById('miniAiMessages');
  if (!messages) return;
  const bubble = document.createElement('div');
  bubble.className = `mini-ai-message ${role}${options.notice ? ' notice' : ''}`;
  bubble.innerHTML = escapeMiniAiText(content);
  if (options.finish) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'mini-ai-finish';
    button.textContent = '大功告成';
    button.addEventListener('click', completeCookingTimer);
    bubble.appendChild(document.createElement('br'));
    bubble.appendChild(button);
  }
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

function parseChineseNumber(value) {
  const text = String(value || '').trim();
  if (/^\d+(?:\.\d+)?$/.test(text)) return Number(text);
  if (text === '半') return 0.5;
  const digits = { 零: 0, 〇: 0, 一: 1, 两: 2, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  const units = { 十: 10, 百: 100, 千: 1000, 万: 10000 };
  let total = 0;
  let current = 0;
  let matched = false;
  for (const char of text) {
    if (Object.prototype.hasOwnProperty.call(digits, char)) {
      current = digits[char];
      matched = true;
    } else if (units[char]) {
      total += (current || 1) * units[char];
      current = 0;
      matched = true;
    }
  }
  return matched ? total + current : null;
}

function parseDurationAmount(amountText, unit) {
  const amount = parseChineseNumber(amountText);
  if (!amount) return null;
  const seconds = unit.includes('时') || unit.includes('小')
    ? amount * 3600
    : (unit.includes('秒') ? amount : amount * 60);
  return { seconds, amount, wasClamped: (unit.includes('时') || unit.includes('小')) && amount > 23 };
}

function parseCookingStartCommand(text) {
  const source = String(text || '').replace(/\s+/g, ' ').trim();
  const startMatch = source.match(/(?:现在|我)?\s*(?:开始|准备|打算|要)\s*(?:做|制作|烹饪|煮|炒|炖|蒸)?\s*(?:个|一道|一份)?\s*([^，。,；;\n]+?)(?=\s*(?:预计|需要|用时|耗时|大约|约)|[，。,；;\n]|$)/i);
  if (!startMatch) return null;
  const dish = startMatch[1].replace(/^(一道|菜品|这道菜)\s*/, '').trim();
  if (!dish) return null;

  const numberPattern = '(\\d{1,3}(?:\\.\\d+)?|[零〇一两二三四五六七八九十百千万半]+)';
  const unitPattern = '(小时|小時|个小时|时|分钟|分|秒)';
  const totalMatch = source.match(new RegExp(`(?:预计|需要|用时|耗时|大约|约|总共|一共)\\s*(?:会|约)?\\s*${numberPattern}\\s*${unitPattern}`, 'i'));
  if (!totalMatch) return null;
  const duration = parseDurationAmount(totalMatch[1], totalMatch[2]);
  if (!duration) return null;

  const stageHints = [];
  const stagePattern = new RegExp(`在\\s*${numberPattern}\\s*${unitPattern}\\s*(?:的时候|时|后)?\\s*(?:提醒我|提示我|告诉我|提醒|提示)?\\s*([^，。,；;\\n]+)`, 'gi');
  let stageMatch;
  while ((stageMatch = stagePattern.exec(source))) {
    const stageDuration = parseDurationAmount(stageMatch[1], stageMatch[2]);
    const instruction = stageMatch[3].trim();
    if (stageDuration && instruction) {
      stageHints.push({ atSeconds: Math.min(86399, Math.max(1, stageDuration.seconds)), instruction });
    }
  }

  return {
    dish,
    durationSeconds: Math.max(1, Math.min(86399, Math.round(duration.seconds))),
    wasClamped: duration.wasClamped,
    stageHints
  };
}

function formatTimerDuration(totalSeconds) {
  const safe = Math.min(86399, Math.max(0, Math.floor(totalSeconds)));
  const hours = String(Math.floor(safe / 3600)).padStart(2, '0');
  const minutes = String(Math.floor((safe % 3600) / 60)).padStart(2, '0');
  const seconds = String(safe % 60).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

function timerStepsFromReply(reply, dish) {
  const parsed = String(reply || '').split(/\n|。/).map(part => part.replace(/^\s*(?:\d+[.、)、]|[-*])\s*/, '').trim()).filter(part => part.length >= 5 && part.length <= 80);
  const defaults = [`准备并处理${dish}的食材`, `开火加热，按口感推进${dish}的烹饪`, `加入调味并检查熟度`, `装盘前再确认一次火候与味道`];
  return [...parsed, ...defaults].slice(0, 4);
}

function buildCookingStageEvents(command, steps) {
  const explicit = (command.stageHints || []).map(item => ({
    atSeconds: Math.min(command.durationSeconds, item.atSeconds),
    instruction: item.instruction
  }));
  if (explicit.length) return explicit.sort((a, b) => a.atSeconds - b.atSeconds);
  return steps.map((step, index) => ({
    atSeconds: Math.max(1, Math.round(command.durationSeconds * (index + 1) / steps.length)),
    instruction: step
  }));
}

function updateCookingTimerDisplay() {
  if (!cookingTimerState) return;
  const elapsed = Math.min(86399, Math.max(0, (Date.now() - cookingTimerState.startedAt) / 1000));
  const value = formatTimerDuration(elapsed);
  const status = cookingTimerState.awaitingCompletion ? '预计时间已到 · 等待完成' : '小 AI 会在阶段节点提醒';
  const displays = [
    ['cookingTimer3D', 'cookingTimerDish', 'cookingTimerValue', 'cookingTimerStatus'],
    ['miniAiTimer', 'miniAiTimerDish', 'miniAiTimerValue', 'miniAiTimerStatus']
  ];
  for (const [containerId, dishId, valueId, statusId] of displays) {
    const container = document.getElementById(containerId);
    if (!container) continue;
    const dish = document.getElementById(dishId);
    const timerValue = document.getElementById(valueId);
    const timerStatus = document.getElementById(statusId);
    if (dish) dish.textContent = cookingTimerState.dish;
    if (timerValue) timerValue.textContent = value;
    if (timerStatus) timerStatus.textContent = status;
    container.classList.remove('hidden');
  }
}

function showMiniAiAttention() {
  openMiniAiPanel();
  const dock = document.getElementById('miniAiDock');
  if (dock) {
    dock.classList.remove('mini-ai-attention');
    void dock.offsetWidth;
    dock.classList.add('mini-ai-attention');
  }
}

function queueCookingStageNotice(step, stageNumber) {
  if (!cookingTimerState || cookingTimerState.awaitingCompletion) return;
  const notice = {
    prompt: `计时提醒：用户正在做「${cookingTimerState.dish}」，现在进入第 ${stageNumber || cookingTimerState.stageIndex + 1} 个阶段。请先回答用户可能正在问的问题，然后用一句清楚的中文告诉用户下一步怎么做：${step || '检查当前火候和熟度'}。不要重置计时器。`,
    fallback: `⏱️ 「${cookingTimerState.dish}」进入下一阶段：${step || '检查当前火候和熟度'}。完成这一步后继续观察火候。`
  };
  if (miniAiBusy) miniAiStageQueue.push(notice);
  else requestCookingStageNotice(notice);
}

async function requestCookingStageNotice(notice) {
  const activeTimer = cookingTimerState;
  showMiniAiAttention();
  try {
    const res = await Api.chatKitchenAssistant({
      message: notice.prompt,
      history: miniAiHistory.slice(-12),
      recipe_context: null,
      memory_summary: null
    });
    if (!cookingTimerState || cookingTimerState !== activeTimer) return;
    const reply = (res.reply || '').trim() || notice.fallback;
    appendMiniAiMessage(reply, 'assistant', { notice: true });
    miniAiHistory.push({ role: 'assistant', content: reply });
  } catch (error) {
    if (!cookingTimerState || cookingTimerState !== activeTimer) return;
    appendMiniAiMessage(notice.fallback, 'assistant', { notice: true });
    miniAiHistory.push({ role: 'assistant', content: notice.fallback });
  }
}

async function flushMiniAiStageQueue() {
  if (miniAiBusy || !miniAiStageQueue.length) return;
  const notice = miniAiStageQueue.shift();
  await requestCookingStageNotice(notice);
  if (!miniAiBusy) await flushMiniAiStageQueue();
}

function finishTimerAwaitingCompletion() {
  if (!cookingTimerState || cookingTimerState.awaitingCompletion) return;
  cookingTimerState.awaitingCompletion = true;
  updateCookingTimerDisplay();
  showMiniAiAttention();
  appendMiniAiMessage(`⏱️ 「${cookingTimerState.dish}」已经达到预计烹饪时间。请确认菜品是否真的完成；完成后点击下面的按钮，计时器才会结束。`, 'assistant', { notice: true, finish: true });
}

function tickCookingTimer() {
  if (!cookingTimerState) return;
  const elapsed = Math.min(86399, Math.max(0, (Date.now() - cookingTimerState.startedAt) / 1000));
  updateCookingTimerDisplay();
  if (elapsed >= cookingTimerState.durationSeconds) {
    finishTimerAwaitingCompletion();
    return;
  }
  while (cookingTimerState.stageIndex < cookingTimerState.stageEvents.length) {
    const event = cookingTimerState.stageEvents[cookingTimerState.stageIndex];
    if (elapsed < event.atSeconds) break;
    cookingTimerState.stageIndex += 1;
    queueCookingStageNotice(event.instruction, cookingTimerState.stageIndex);
  }
}

function startCookingTimer(command, initialReply = '') {
  stopCookingTimer(true);
  const steps = timerStepsFromReply(initialReply, command.dish);
  cookingTimerState = {
    dish: command.dish,
    durationSeconds: command.durationSeconds,
    startedAt: Date.now(),
    stageIndex: 0,
    steps,
    stageEvents: buildCookingStageEvents(command, steps),
    awaitingCompletion: false
  };
  updateCookingTimerDisplay();
  cookingTimerInterval = window.setInterval(tickCookingTimer, 1000);
  showMiniAiAttention();
  const capTip = command.wasClamped ? '（计时上限为 23 小时 59 分 59 秒）' : '';
  appendMiniAiMessage(`⏱️ 已开始为「${command.dish}」计时 ${formatTimerDuration(command.durationSeconds)}${capTip}。我会在每个阶段提醒你下一步。`, 'assistant', { notice: true });
}

function stopCookingTimer(silent = false) {
  if (cookingTimerInterval) window.clearInterval(cookingTimerInterval);
  cookingTimerInterval = null;
  cookingTimerState = null;
  miniAiStageQueue = [];
  document.getElementById('cookingTimer3D')?.classList.add('hidden');
  document.getElementById('miniAiTimer')?.classList.add('hidden');
}

function completeCookingTimer() {
  if (!cookingTimerState) return;
  const elapsed = Math.min(86399, Math.max(0, (Date.now() - cookingTimerState.startedAt) / 1000));
  const dish = cookingTimerState.dish;
  stopCookingTimer();
  showMiniAiAttention();
  appendMiniAiMessage(`🎉 大功告成！「${dish}」本次实际计时 ${formatTimerDuration(elapsed)}。趁热享用，记得及时核对食材消耗。`, 'assistant', { notice: true });
}

async function sendMiniAiMessage(forcedMessage = null) {
  const input = document.getElementById('miniAiInput');
  const text = (forcedMessage || input?.value || '').trim();
  if (!text || miniAiBusy) return;
  if (!forcedMessage && input) input.value = '';
  appendMiniAiMessage(text, 'user');
  miniAiHistory.push({ role: 'user', content: text });
  const cookingCommand = parseCookingStartCommand(text);
  if (cookingCommand) startCookingTimer(cookingCommand);
  miniAiBusy = true;
  const sendBtn = document.getElementById('miniAiSendBtn');
  if (sendBtn) sendBtn.disabled = true;
  try {
    const res = await Api.chatKitchenAssistant({
      message: text,
      history: miniAiHistory.slice(-12, -1),
      recipe_context: null,
      memory_summary: null
    });
    const reply = (res.reply || '').trim() || '我暂时没有生成有效回答，请再问我一次。';
    appendMiniAiMessage(reply, 'assistant', { notice: res.is_refused });
    miniAiHistory.push({ role: 'assistant', content: reply });
    if (res.actions_executed?.length) {
      await refreshShoppingBadge();
      await loadPantryItems();
    }
  } catch (error) {
    appendMiniAiMessage(`连接厨房 AI 失败：${error.message || '请稍后重试'}`, 'assistant', { notice: true });
  } finally {
    miniAiBusy = false;
    if (sendBtn) sendBtn.disabled = false;
    await flushMiniAiStageQueue();
  }
}

window.toggleMiniAi = function() {
  const panel = document.getElementById('miniAiPanel');
  if (!panel) return;
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) openMiniAiPanel();
};

function formatImageRecipeResult(data) {
  if (!data.is_dish) return data.reply || '这张图片与菜品无关，我无法根据它生成菜谱。';
  const ingredients = (data.ingredients_needed || []).map(item => `${item.name || '食材'}（${item.amount || '适量'}）`).join('、') || '根据图片推测的常见食材';
  const steps = (data.cooking_steps || []).map((step, index) => `${index + 1}. ${step}`).join('\n') || '请根据图片中的食材处理后烹饪至熟透。';
  return `图片识别到：${data.recipe_name}\n难度与时间：${data.difficulty}\n食材：${ingredients}\n步骤：\n${steps}\n大厨提示：${data.chef_tips || '注意火候并确认食材熟透。'}`;
}

window.handleRecipeImageUpload = async function(event, target = 'chat') {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  const isMini = target === 'mini';
  const append = (content, role = 'assistant', options = {}) => isMini ? appendMiniAiMessage(content, role, options) : appendChatMessage(role, content, options.notice);
  append(`📷 正在识别图片：${file.name}`, 'user');
  if (isMini) miniAiHistory.push({ role: 'user', content: `上传了一张菜品图片：${file.name}` });
  else chatHistory.push({ role: 'user', content: `上传了一张菜品图片：${file.name}` });
  try {
    const data = await Api.recipeFromImage(file);
    const reply = formatImageRecipeResult(data);
    append(reply, 'assistant', { notice: !data.is_dish });
    if (isMini) miniAiHistory.push({ role: 'assistant', content: reply });
    else {
      chatHistory.push({ role: 'assistant', content: reply });
      sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatHistory));
    }
  } catch (error) {
    append(`图片识别失败：${error.message || '请换一张清晰的菜品图片'}`, 'assistant', { notice: true });
  }
};

function enableMiniAiDrag() {
  const dock = document.getElementById('miniAiDock');
  const bubble = document.getElementById('miniAiBubble');
  if (!dock || !bubble) return;
  let dragging = false;
  let offsetY = 0;
  bubble.addEventListener('pointerdown', event => {
    dragging = true;
    miniAiDragMoved = false;
    const rect = dock.getBoundingClientRect();
    offsetY = event.clientY - rect.top;
    bubble.setPointerCapture?.(event.pointerId);
  });
  bubble.addEventListener('pointermove', event => {
    if (!dragging) return;
    miniAiDragMoved = true;
    const bubbleHeight = dock.offsetHeight || 82;
    const minTop = 12;
    const maxTop = Math.max(minTop, window.innerHeight - bubbleHeight - 12);
    const top = Math.min(maxTop, Math.max(minTop, event.clientY - offsetY));
    dock.style.top = `${top}px`;
    dock.style.bottom = 'auto';
    keepMiniAiDockInViewport();
  });
  const finishDrag = () => { dragging = false; window.setTimeout(() => { miniAiDragMoved = false; }, 0); };
  bubble.addEventListener('pointerup', finishDrag);
  bubble.addEventListener('pointercancel', finishDrag);
  bubble.addEventListener('click', () => { if (!miniAiDragMoved) window.toggleMiniAi(); });
  window.addEventListener('resize', keepMiniAiDockInViewport);
}

// 主工作区独立大页面切换
window.switchMainView = async function(view) {
  currentMainView = view;
  const views = ['fridge', 'community', 'carbon', 'chat'];

  views.forEach(v => {
    const sec = document.getElementById(`view${capitalize(v)}`);
    if (sec) sec.classList.toggle("hidden", v !== view);

    const navBtn = document.getElementById(`navBtn${capitalize(v)}`);
    if (navBtn) {
      if (v === view) {
        navBtn.className = "w-full flex items-center space-x-3 px-4 py-2.5 rounded-xl font-bold text-emerald-800 bg-emerald-50 transition border border-emerald-200 shadow-2xs";
      } else {
        navBtn.className = "w-full flex items-center space-x-3 px-4 py-2.5 rounded-xl font-medium text-slate-600 hover:bg-slate-50 hover:text-slate-900 transition";
      }
    }
  });

  if (view === 'fridge') {
    await loadPantryItems();
  } else if (view === 'community') {
    await loadCommunityFeed();
  } else if (view === 'carbon') {
    await loadCarbonLeaderboard();
  } else if (view === 'chat') {
    const input = document.getElementById("chatUserInput");
    if (input) input.focus();
    scrollChatToBottom();
  }
};

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ==================== 3. 登录认证与状态同步 ====================
window.showForceAuthModal = function() {
  setMiniAiVisible(false);
  fridgeItems = [];
  fridge3D?.setItems([]);
  setUpperDoor(false);
  setLowerDoor(false);
  document.getElementById("authModal")?.classList.remove("hidden");

  const un = document.getElementById("currentUserName");
  if (un) un.textContent = "未登录";

  const rb = document.getElementById("userRoleBadge");
  if (rb) {
    rb.textContent = "访客";
    rb.className = "text-[10px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-600 font-bold";
  }

  const ab = document.getElementById("authActionBtn");
  if (ab) {
    ab.innerHTML = `<span>🔑</span> <span>登录 / 注册</span>`;
    ab.onclick = () => window.openAuthModal();
  }
};

window.openAuthModal = () => {
  window.switchAuthMode('login');
  const tip = document.getElementById("authErrorTip");
  if (tip) tip.textContent = "";
  document.getElementById("authModal")?.classList.remove("hidden");
};

window.ensureAuth = function(actionCallback) {
  const token = localStorage.getItem("freshplate_token");
  if (!token || !currentUser) {
    window.showForceAuthModal();
    return;
  }
  if (typeof actionCallback === 'function') {
    actionCallback();
  }
};

window.switchAuthMode = function(mode) {
  currentAuthMode = mode;
  const title = document.getElementById("authModalTitle");
  const tabLogin = document.getElementById("tabBtnLogin");
  const tabRegister = document.getElementById("tabBtnRegister");
  const submitBtn = document.getElementById("authSubmitBtn");
  const switchTip = document.getElementById("authSwitchTipBtn");
  const userLabel = document.getElementById("authUsernameLabel");
  const pwdLabel = document.getElementById("authPasswordLabel");
  const errorEl = document.getElementById("authErrorTip");

  if (errorEl) errorEl.textContent = "";

  if (mode === 'login') {
    if (title) title.textContent = "账号登录";
    if (tabLogin) tabLogin.className = "flex-1 py-1.5 rounded-xl text-xs font-bold transition bg-white text-slate-800 shadow-sm";
    if (tabRegister) tabRegister.className = "flex-1 py-1.5 rounded-xl text-xs font-bold transition text-slate-500 hover:text-slate-800";
    if (userLabel) userLabel.textContent = "账号";
    if (pwdLabel) pwdLabel.textContent = "密码";
    if (submitBtn) {
      submitBtn.textContent = "立即登录";
      submitBtn.className = "w-full py-3 bg-cyan-600 hover:bg-cyan-700 text-white rounded-xl text-xs font-bold transition shadow-md";
    }
    if (switchTip) switchTip.textContent = "还没有账号？点击注册新账号";
  } else {
    if (title) title.textContent = "注册新用户";
    if (tabRegister) tabRegister.className = "flex-1 py-1.5 rounded-xl text-xs font-bold transition bg-white text-slate-800 shadow-sm";
    if (tabLogin) tabLogin.className = "flex-1 py-1.5 rounded-xl text-xs font-bold transition text-slate-500 hover:text-slate-800";
    if (userLabel) userLabel.textContent = "设置账号";
    if (pwdLabel) pwdLabel.textContent = "设置密码";
    if (submitBtn) {
      submitBtn.textContent = "确认注册并登录";
      submitBtn.className = "w-full py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition shadow-md";
    }
    if (switchTip) switchTip.textContent = "已有账号？点击返回登录";
  }
};

window.toggleAuthMode = function() {
  window.switchAuthMode(currentAuthMode === 'login' ? 'register' : 'login');
};

function parseErrorMessage(errData) {
  if (!errData) return "操作失败，请重试";
  if (typeof errData === 'string') return errData;
  if (typeof errData.detail === 'string') return errData.detail;
  return "数据格式有误，请核对输入";
}

window.handleAuthSubmit = async function() {
  const u = document.getElementById("authUsername").value.trim();
  const p = document.getElementById("authPassword").value.trim();
  const errorEl = document.getElementById("authErrorTip");
  errorEl.textContent = "";

  if (!u || !p) {
    errorEl.textContent = "请完整输入账号与密码";
    return;
  }

  const isLogin = currentAuthMode === 'login';
  const submitBtn = document.getElementById("authSubmitBtn");
  submitBtn.disabled = true;
  submitBtn.textContent = isLogin ? "正在登录..." : "正在注册...";

  try {
    const res = isLogin ? await Api.login(u, p) : await Api.register(u, p);
    if (res.access_token) {
      localStorage.setItem("freshplate_token", res.access_token);
      localStorage.setItem("freshplate_role", res.role);

      if (res.role === 'admin' || res.role === 'super_admin') {
        window.location.href = "/admin.html";
        return;
      }

      document.getElementById("authUsername").value = "";
      document.getElementById("authPassword").value = "";
      await checkAuthAndBootstrap();

      if (!isLogin) {
        window.openOnboardingModal();
      }
    } else {
      errorEl.textContent = parseErrorMessage(res);
    }
  } catch (err) {
    errorEl.textContent = err.message || "服务连接失败";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = isLogin ? "立即登录" : "确认注册并登录";
  }
};

window.logoutUser = function() {
  localStorage.removeItem("freshplate_token");
  localStorage.removeItem("freshplate_role");
  currentUser = null;
  miniAiHistory = [];
  stopCookingTimer(true);
  document.getElementById("refrigerationGrid").innerHTML = "";
  document.getElementById("freezerGrid").innerHTML = "";
  document.getElementById("refrigCount").textContent = "0 件食品";
  document.getElementById("freezerCount").textContent = "0 件食品";
  window.showForceAuthModal();
};

async function checkAuthAndBootstrap() {
  const token = localStorage.getItem("freshplate_token");
  if (!token) {
    window.showForceAuthModal();
    return;
  }

  try {
    const me = await Api.getMe();
    currentUser = me;

    if (me.role === 'admin' || me.role === 'super_admin') {
      window.location.href = "/admin.html";
      return;
    }

    document.getElementById("authModal")?.classList.add("hidden");
    setMiniAiVisible(true);

    const userLabel = document.getElementById("currentUserName");
    const roleBadge = document.getElementById("userRoleBadge");
    const authBtn = document.getElementById("authActionBtn");

    if (userLabel) userLabel.textContent = `👤 ${me.username}`;
    if (roleBadge) {
      roleBadge.textContent = "个人空间";
      roleBadge.className = "text-[10px] px-2 py-0.5 rounded-full bg-cyan-100 text-cyan-700 font-bold";
    }
    if (authBtn) {
      authBtn.innerHTML = `<span>🚪</span> <span>退出当前账号</span>`;
      authBtn.onclick = () => window.logoutUser();
    }

    await loadPantryItems();
    await refreshShoppingBadge();
    await loadRecipeOptions();
    restoreChatMemory();
  } catch (err) {
    currentUser = null;
    window.showForceAuthModal();
  }
}

// ==================== 4. 健康画像 ====================
window.openOnboardingModal = () => window.openModal("onboardingHealthModal");
window.skipOnboardingHealth = () => window.closeModal("onboardingHealthModal");

window.submitOnboardingHealth = async function() {
  const customText = document.getElementById("onboardingConditionsInput")?.value.trim() || "";
  const notes = document.getElementById("onboardingNotesInput")?.value.trim() || "";

  if (!customText) return alert("请简要输入您的身体状况或饮食忌口！");
  const tags = customText.split(/[,，、\s]+/).filter(Boolean);

  try {
    await Api.createHealthProfile({
      member_name: "本人",
      relation: "self",
      conditions: tags,
      dietary_notes: notes,
      is_primary: 1
    });
    alert("🎉 身体健康画像已保存！AI 大厨将主动为您规避不适食材。");
    window.closeModal("onboardingHealthModal");
  } catch (err) {
    alert("保存失败: " + err.message);
  }
};

window.openHealthProfileModal = async function() {
  window.openModal("healthProfileModal");
  await refreshHealthProfilesList();
};

async function refreshHealthProfilesList() {
  const container = document.getElementById("healthProfilesListContainer");
  if (!container) return;
  container.innerHTML = '<div class="text-xs text-slate-400 py-4 text-center">加载健康档案中...</div>';

  try {
    const list = await Api.getHealthProfiles();
    if (!list.length) {
      container.innerHTML = '<div class="text-xs text-slate-400 py-4 text-center">暂无健康画像，请在下方自由填写您或家人的健康状况</div>';
      return;
    }

    container.innerHTML = list.map(p => `
      <div class="p-3 bg-white border border-slate-200 rounded-xl flex items-center justify-between shadow-xs">
        <div>
          <div class="flex items-center gap-2">
            <span class="font-bold text-slate-800 text-xs">${p.member_name}</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded ${p.is_primary ? 'bg-emerald-50 text-emerald-600 font-bold' : 'bg-slate-100 text-slate-500'}">
              ${p.relation === 'self' ? '本人' : '家属'}
            </span>
          </div>
          <div class="flex flex-wrap gap-1 mt-1">
            ${(p.conditions || []).map(c => `<span class="text-[10px] px-1.5 py-0.5 bg-rose-50 text-rose-600 rounded">${c}</span>`).join('') || '<span class="text-[10px] text-slate-400">体质健康</span>'}
          </div>
          ${p.dietary_notes ? `<p class="text-[11px] text-slate-400 mt-0.5">备忘: ${p.dietary_notes}</p>` : ''}
        </div>
        <button onclick="deleteHealthMember(${p.id})" class="text-xs text-red-500 hover:text-red-700 px-2 py-1">删除</button>
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<div class="text-xs text-red-400 py-4 text-center">获取档案失败</div>';
  }
}

window.addNewHealthProfile = async function(e) {
  e.preventDefault();
  const name = document.getElementById("newMemberName").value.trim();
  const relation = document.getElementById("newMemberRelation").value;
  const isPrimary = document.getElementById("newMemberPrimary")?.checked ? 1 : 0;
  const conditionInput = document.getElementById("newMemberConditionInput").value.trim();
  const notes = document.getElementById("newMemberNotes").value.trim();

  if (!name || !conditionInput) return alert("请填写称呼及身体状况！");
  const tags = conditionInput.split(/[,，、\s]+/).filter(Boolean);

  try {
    await Api.createHealthProfile({
      member_name: name,
      relation: relation,
      conditions: tags,
      dietary_notes: notes,
      is_primary: isPrimary
    });
    alert(`成员「${name}」的健康画像已添加！`);
    document.getElementById("newMemberName").value = "";
    document.getElementById("newMemberConditionInput").value = "";
    document.getElementById("newMemberNotes").value = "";
    await refreshHealthProfilesList();
  } catch (err) {
    alert("添加失败: " + err.message);
  }
};

window.deleteHealthMember = async function(id) {
  if (!confirm("确定删除该家庭成员的健康档案吗？")) return;
  try {
    await Api.deleteHealthProfile(id);
    await refreshHealthProfilesList();
  } catch (err) {
    alert("删除失败: " + err.message);
  }
};

// ==================== 5. 冰箱食材展示 (防溢出) ====================
export async function loadPantryItems() {
  try {
    const items = await Api.getPantryItems();
    const refrigGrid = document.getElementById("refrigerationGrid");
    const freezerGrid = document.getElementById("freezerGrid");
    if (!refrigGrid || !freezerGrid) return;

    refrigGrid.innerHTML = "";
    freezerGrid.innerHTML = "";

    let refrigCount = 0;
    let freezerCount = 0;

    items.forEach(item => {
      if (item.location === "refrigeration") refrigCount++;
      else freezerCount++;

      const card = createFoodCard(item);
      if (item.location === "refrigeration") refrigGrid.appendChild(card);
      else freezerGrid.appendChild(card);
    });

    document.getElementById("refrigCount").textContent = `${refrigCount} 件食品`;
    document.getElementById("freezerCount").textContent = `${freezerCount} 件食品`;
    fridgeItems = items;
    fridge3D?.setItems(items);
    if (!refrigCount) refrigGrid.innerHTML = '<p class="fridge-empty">冷藏室暂无食材</p>';
    if (!freezerCount) freezerGrid.innerHTML = '<p class="fridge-empty">冷冻室暂无食材</p>';
  } catch (err) {
    console.warn("加载食材异常:", err);
  }
}
window.loadPantryItems = loadPantryItems;

function createFoodCard(item) {
  const article = document.createElement("article");
  let statusBadge = "";
  let glowClass = "border border-slate-200 bg-white hover:border-emerald-400";

  if (item.is_expired) {
    glowClass = "expired-danger-stripes";
    statusBadge = `<span class="px-2 py-0.5 rounded-full bg-red-600 text-white text-[10px] font-black uppercase tracking-wider flex items-center gap-1 shadow-sm shrink-0"><span class="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>已过期</span>`;
  } else if (item.hours_left < 24) {
    glowClass = "border-2 border-red-400 bg-red-50/50 light-danger-glow";
    statusBadge = `<span class="px-1.5 py-0.5 rounded-full bg-red-500 text-white text-[10px] font-bold shrink-0 animate-pulse">临期 (<1天)</span>`;
  } else if (item.hours_left <= 48) {
    glowClass = "border border-amber-300 bg-amber-50/50 light-warning-glow";
    statusBadge = `<span class="px-1.5 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-bold shrink-0">尽快食用 (1-2天)</span>`;
  } else {
    glowClass = "border border-emerald-200 bg-white hover:border-emerald-400 shadow-sm";
    statusBadge = `<span class="px-1.5 py-0.5 rounded-full bg-emerald-500 text-white text-[10px] font-bold shrink-0">新鲜 (>2天)</span>`;
  }

  // 严格增加 overflow-hidden 保护与弹性自适应内高，杜绝底边字样下漏
  article.className = `cursor-pointer relative flex flex-col justify-between p-3 rounded-2xl transition-all duration-200 hover:scale-[1.02] shadow-sm min-h-[155px] overflow-hidden ${glowClass}`;

  const imgHtml = item.image_url
    ? `<img src="${item.image_url}" alt="${item.name}" class="w-10 h-10 rounded-lg object-cover border border-slate-200 shadow-inner shrink-0" />`
    : `<div class="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center text-lg shrink-0">🥗</div>`;

  const dateStr = item.expire_at ? item.expire_at.split(' ')[0] : "--";

  article.innerHTML = `
    <div class="min-w-0 flex-1">
      <div class="flex justify-between items-start gap-1">
        ${imgHtml}
        ${statusBadge}
      </div>
      <h4 class="font-bold text-sm text-slate-800 mt-2 truncate" title="${item.name}">${item.name}</h4>
      <p class="text-xs text-slate-500 mt-0.5 truncate">剩余: <strong class="text-emerald-600">${item.remaining_weight} ${item.unit}</strong></p>
    </div>
    <div class="text-[10px] font-medium pt-1.5 mt-2 border-t border-slate-100 flex justify-between items-center ${item.is_expired ? 'text-red-600 font-bold' : 'text-slate-400'}">
      <span class="truncate w-full block" title="${item.is_expired ? '⚠️ 严禁食用 · 点击丢弃' : '保质至: ' + dateStr}">
        ${item.is_expired ? '⚠️ 严禁食用 · 点击丢弃' : `保质至: ${dateStr}`}
      </span>
    </div>
  `;

  article.onclick = () => openFoodDetail(item);
  return article;
}

function openFoodDetail(item) {
  currentActiveItem = item;
  document.getElementById("modalFoodTitle").textContent = item.name;
  document.getElementById("modalFoodLocation").textContent = `位置：${item.location === 'refrigeration' ? '上层 · 果蔬保鲜室' : '下层 · 深冷冷冻室'}`;
  document.getElementById("modalRemainingWeight").textContent = item.remaining_weight;
  document.getElementById("modalWeightUnit").textContent = item.unit;
  document.getElementById("modalExpiryText").textContent = `截止时间：${item.expire_at}`;

  const deductUnit = document.getElementById("deductUnitLabel");
  if (deductUnit) deductUnit.textContent = item.unit || "克";

  const usedInput = document.getElementById("usedWeightInput");
  if (usedInput) usedInput.value = "";

  const imgSlot = document.getElementById("modalFoodImgSlot");
  if (item.image_url) {
    imgSlot.innerHTML = `<img src="${item.image_url}" alt="${item.name}" class="w-full h-full object-cover" />`;
  } else {
    imgSlot.innerHTML = `<span class="text-xs text-slate-400">暂无实图</span>`;
  }

  const expiredWarning = document.getElementById("modalExpiredWarning");
  const normalAiStage = document.getElementById("normalAiStage");
  document.getElementById("aiStageRecipeResult").classList.add("hidden");

  if (item.is_expired) {
    expiredWarning.classList.remove("hidden");
    normalAiStage.classList.add("hidden");
  } else {
    expiredWarning.classList.add("hidden");
    normalAiStage.classList.remove("hidden");
    renderSubCuisinesAndMethods("pantry", document.getElementById("pantryRecipeCuisineSelect")?.value || "chinese");
  }

  window.openModal("foodDetailModal");
}

window.discardCurrentItem = async function() {
  if (!currentActiveItem) return;
  if (!confirm(`确认将已过期的「${currentActiveItem.name}」丢弃并彻底删除吗？`)) return;

  const res = await Api.discardItem(currentActiveItem.id);
  if (res.ok) {
    window.closeModal("foodDetailModal");
    loadPantryItems();
  } else {
    alert("丢弃失败");
  }
};

function compressImage(file, maxDimension = 1024, quality = 0.8) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = (e) => {
      const img = new Image();
      img.src = e.target.result;
      img.onload = () => {
        let width = img.width;
        let height = img.height;
        if (width > maxDimension || height > maxDimension) {
          if (width > height) {
            height = Math.round((height * maxDimension) / width);
            width = maxDimension;
          } else {
            width = Math.round((width * maxDimension) / height);
            height = maxDimension;
          }
        }
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob((blob) => resolve(blob || file), 'image/jpeg', quality);
      };
      img.onerror = () => resolve(file);
    };
    reader.onerror = () => resolve(file);
  });
}

window.handleFoodImageSelect = function(e) {
  const file = e.target.files[0];
  const previewBox = document.getElementById("foodImagePreviewBox");
  const previewImg = document.getElementById("foodImagePreviewImg");
  if (file && previewBox && previewImg) {
    const reader = new FileReader();
    reader.onload = (evt) => {
      previewImg.src = evt.target.result;
      previewBox.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
  }
};

window.clearFoodImage = function() {
  const fileInput = document.getElementById("fileInput");
  if (fileInput) fileInput.value = "";
  window.lastUploadedImgUrl = null;
  const previewBox = document.getElementById("foodImagePreviewBox");
  if (previewBox) previewBox.classList.add("hidden");
};

window.recognizePhoto = async function() {
  const fileInput = document.getElementById("fileInput");
  if (!fileInput.files || fileInput.files.length === 0) return alert("请先选择食材图片！");

  const btn = document.getElementById("btnRecognize");
  btn.innerText = "⚡ AI 分析中...";
  btn.disabled = true;

  try {
    const rawFile = fileInput.files[0];
    const compressedBlob = await compressImage(rawFile, 1024, 0.8);
    const formData = new FormData();
    formData.append("file", compressedBlob, rawFile.name || "food.jpg");

    const data = await Api.recognizeFood(formData);

    const nameInput = document.getElementById("foodNameInput");
    if (data.food_name) nameInput.value = data.food_name;

    const layerSelect = document.getElementById("foodLayerSelect");
    let targetLayer = (data.location || "refrigeration").toLowerCase();
    if (targetLayer.includes("freezer") || targetLayer.includes("冻")) {
      layerSelect.value = "freezer";
    } else {
      layerSelect.value = "refrigeration";
    }

    currentAiShelfRefrig = parseFloat(data.shelf_life_days_refrig || 3.0);
    currentAiShelfFreezer = parseFloat(data.shelf_life_days_freezer || 45.0);

    const shelfInput = document.getElementById("shelfLifeInput");
    shelfInput.value = (layerSelect.value === "freezer") ? currentAiShelfFreezer : currentAiShelfRefrig;

    window.lastUploadedImgUrl = data.image_url;
    document.getElementById("foodWeightInput").focus();
  } catch (err) {
    alert("AI 识别响应异常，可手动输入食材信息。");
  } finally {
    btn.innerText = "🤖 开始多模态 AI 智能识别";
    btn.disabled = false;
  }
};

window.submitPantryItem = async function(e) {
  e.preventDefault();
  const name = document.getElementById("foodNameInput").value.trim();
  const rawWeight = parseFloat(document.getElementById("foodWeightInput").value);
  const shelfDays = parseFloat(document.getElementById("shelfLifeInput").value);

  if (!name || isNaN(rawWeight) || isNaN(shelfDays)) return alert("请填写完整食材信息！");

  const weight = Math.round(rawWeight * 100) / 100;
  const layer = document.getElementById("foodLayerSelect").value;

  const payload = {
    name,
    location: layer,
    initial_weight: weight,
    remaining_weight: weight,
    unit: document.getElementById("foodUnitSelect").value,
    shelf_life_days: shelfDays,
    image_url: window.lastUploadedImgUrl || null
  };

  try {
    const res = await Api.addPantryItem(payload);
    if (res.ok || res.status === 200) {
      alert(`🎉 食材「${name}」已成功存入冰箱！`);
      window.closeModal("uploadModal");
      window.clearFoodImage();
      document.getElementById("foodNameInput").value = "";
      document.getElementById("foodWeightInput").value = "";
      await loadPantryItems();
      if (layer === "refrigeration") setUpperDoor(true);
      else setLowerDoor(true);
    } else {
      const errJson = await res.json().catch(() => ({}));
      alert(`⚠️ 存入失败：${parseErrorMessage(errJson)}`);
    }
  } catch (err) {
    alert(`⚠️ 请求异常：${err.message}`);
  }
};

// ==================== 6. 菜系风味与烹饪技法配置 ====================
async function loadRecipeOptions() {
  try {
    recipeOptionsData = await Api.getRecipeOptions();
    initCuisineAndMethodSection("pantry");
    initCuisineAndMethodSection("special");
    initCuisineAndMethodSection("todayEat");
  } catch (e) {
    console.warn("拉取菜谱选项配置失败:", e);
  }
}

window.handleCuisineChange = function(scope) {
  const cuisine = document.getElementById(`${scope}RecipeCuisineSelect`)?.value || "chinese";
  renderSubCuisinesAndMethods(scope, cuisine);
};

function renderSubCuisinesAndMethods(scope, cuisine) {
  if (!recipeOptionsData) return;
  const data = recipeOptionsData[cuisine] || recipeOptionsData["chinese"];

  const subSelect = document.getElementById(`${scope}RecipeSubCuisineSelect`);
  const methodSelect = document.getElementById(`${scope}RecipeCookingMethodSelect`);

  if (subSelect) {
    const defaultLabel = cuisine === "chinese" ? "中式家常 (通用经典风味)" : "经典西式 (通用经典西式风味)";
    subSelect.innerHTML = `<option value="">${defaultLabel}</option>` +
      (data.cuisines || []).map(c => `<option value="${c.name}">${c.name}</option>`).join('');
  }

  if (methodSelect) {
    methodSelect.innerHTML = `<option value="">大厨推荐 (自由选择最适宜技法)</option>` +
      (data.methods || []).map(m => {
        const shortTitle = m.text.includes("】") ? (m.text.split("】")[0] + "】") : m.text;
        return `<option value="${m.key}">${shortTitle}</option>`;
      }).join('');
  }

  updateDescCard(scope, 'cuisine');
  updateDescCard(scope, 'method');
}

window.updateDescCard = function(scope, type) {
  if (!recipeOptionsData) return;
  const cuisine = document.getElementById(`${scope}RecipeCuisineSelect`)?.value || "chinese";
  const data = recipeOptionsData[cuisine] || recipeOptionsData["chinese"];

  if (type === 'cuisine') {
    const subVal = document.getElementById(`${scope}RecipeSubCuisineSelect`)?.value;
    const card = document.getElementById(`${scope}SubCuisineDescCard`);
    if (!card) return;

    if (!subVal) {
      const defaultDesc = cuisine === "chinese"
        ? "【经典中式家常】五味调和，突出食材原汁原味，注重鲜香适口与荤素营养平衡。"
        : "【经典西式家常】注重原汁原味、香草提鲜与基础煎烤烘焙，突显食材本身天然质感。";
      card.innerHTML = `<p class="text-[11px] text-slate-500 leading-relaxed break-words whitespace-normal">${defaultDesc}</p>`;
    } else {
      const found = (data.cuisines || []).find(c => c.name === subVal);
      if (found) {
        card.innerHTML = `<p class="text-[11px] text-slate-700 leading-relaxed break-words whitespace-normal"><strong class="text-emerald-700 font-bold">【${found.name}】</strong>${found.desc}</p>`;
      }
    }
  } else if (type === 'method') {
    const methodVal = document.getElementById(`${scope}RecipeCookingMethodSelect`)?.value;
    const card = document.getElementById(`${scope}MethodDescCard`);
    if (!card) return;

    if (!methodVal) {
      card.innerHTML = `<p class="text-[11px] text-slate-500 leading-relaxed break-words whitespace-normal"><strong class="text-slate-800">【大厨推荐】</strong>由 AI 大厨根据在库食材质地、水分与保鲜紧迫度，自动匹配最锁鲜出香的火候技法。</p>`;
    } else {
      const found = (data.methods || []).find(m => m.key === methodVal);
      if (found) {
        card.innerHTML = `<p class="text-[11px] text-emerald-800 leading-relaxed break-words whitespace-normal font-medium">${found.text}</p>`;
      }
    }
  }
};

function initCuisineAndMethodSection(scope) {
  const cuisineSel = document.getElementById(`${scope}RecipeCuisineSelect`);
  if (cuisineSel) {
    cuisineSel.addEventListener("change", () => window.handleCuisineChange(scope));
  }
  const subSel = document.getElementById(`${scope}RecipeSubCuisineSelect`);
  if (subSel) {
    subSel.addEventListener("change", () => window.updateDescCard(scope, 'cuisine'));
  }
  const methodSel = document.getElementById(`${scope}RecipeCookingMethodSelect`);
  if (methodSel) {
    methodSel.addEventListener("change", () => window.updateDescCard(scope, 'method'));
  }
  renderSubCuisinesAndMethods(scope, "chinese");
}

// ==================== 7. 常规在库食材 AI 菜谱生成 ====================
window.requestAIRecipe = async function(peopleCount) {
  if (!currentActiveItem) return;
  const btn = event.currentTarget;
  btn.textContent = "推演中...";
  btn.disabled = true;

  const cuisine = document.getElementById("pantryRecipeCuisineSelect")?.value || "chinese";
  const subCuisine = document.getElementById("pantryRecipeSubCuisineSelect")?.value || "";
  const cookingMethod = document.getElementById("pantryRecipeCookingMethodSelect")?.value || "";
  const cookingTime = document.getElementById("pantryRecipeCookingTimeSelect")?.value || "";
  const mealType = document.getElementById("pantryRecipeMealTypeSelect")?.value || "dinner";

  try {
    const res = await Api.getAIRecipe(currentActiveItem.id, peopleCount, {
      cuisine,
      sub_cuisine: subCuisine,
      cooking_method: cookingMethod,
      cooking_time: cookingTime,
      meal_type: mealType
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.detail || "生成失败");
      return;
    }
    const recipe = await res.json();
    lastGeneratedRecipe = recipe;

    document.getElementById("aiRecipeTitle").textContent = recipe.recipe_name;
    document.getElementById("aiRecipeDifficultyTag").textContent = `${recipe.difficulty} (${peopleCount}人份)`;
    document.getElementById("aiRecipePantryMatch").textContent = `✓ 搭配理由：${recipe.pantry_match_reason}`;
    document.getElementById("aiRecipeStaples").textContent = `常备调料：${recipe.pantry_staples}`;
    document.getElementById("aiChefTipsText").textContent = recipe.chef_tips;

    const stepsContainer = document.getElementById("aiStepsList");
    stepsContainer.innerHTML = (recipe.cooking_steps || []).map((step, idx) => `
      <div class="p-2 bg-slate-50 rounded-lg border border-slate-200 text-slate-700 text-xs">
        <strong class="text-amber-600">${idx + 1}.</strong> ${step}
      </div>
    `).join("");

    const batchBtn = document.getElementById("btnTriggerBatchDeduct");
    if (batchBtn) {
      batchBtn.onclick = () => window.checkAndPromptIngredientsDeduct(recipe.recipe_name, recipe.ingredients_needed);
    }

    const detailBtn = document.getElementById("btnPantryRecipeDetailedChat");
    if (detailBtn) {
      detailBtn.onclick = () => window.jumpToDetailedRecipeChat(recipe.recipe_name, recipe, 'pantry');
    }

    setupStarButton("btnSaveCurrentRecipeStar", recipe.recipe_name, recipe);
    document.getElementById("aiStageRecipeResult").classList.remove("hidden");
  } catch (err) {
    alert("菜谱规划网络异常");
  } finally {
    btn.textContent = `${peopleCount} 人份`;
    btn.disabled = false;
  }
};

// 收藏按钮样式增加 whitespace-nowrap inline-flex，彻底消除竖排折行
async function setupStarButton(buttonId, recipeName, recipeData) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;

  try {
    allFavoritesCache = await Api.getFavorites();
  } catch (e) {}

  let isFav = allFavoritesCache.some(f => f.recipe_name.trim() === recipeName.trim());

  function renderStarUI() {
    if (isFav) {
      btn.innerHTML = `<span class="text-amber-400 text-sm leading-none">★</span><span class="text-xs font-bold text-amber-600 whitespace-nowrap">已收藏</span>`;
      btn.className = "px-2.5 py-1 bg-amber-50 border border-amber-200 text-amber-700 rounded-lg text-xs font-bold shadow-2xs transition inline-flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0";
    } else {
      btn.innerHTML = `<span class="text-slate-400 text-sm leading-none">☆</span><span class="text-xs font-medium text-slate-600 whitespace-nowrap">收藏</span>`;
      btn.className = "px-2.5 py-1 bg-white border border-slate-200 text-slate-700 hover:border-amber-300 rounded-lg text-xs font-medium shadow-2xs transition inline-flex items-center gap-1 cursor-pointer whitespace-nowrap shrink-0";
    }
  }

  renderStarUI();

  btn.onclick = async () => {
    try {
      if (isFav) {
        await Api.deleteFavoriteByName(recipeName);
        isFav = false;
        renderStarUI();
        allFavoritesCache = allFavoritesCache.filter(f => f.recipe_name.trim() !== recipeName.trim());
      } else {
        const isLowFat = (recipeData.category === 'low_fat');
        const cal = isLowFat ? (recipeData.health_metric || recipeData.calories) : (recipeData.calories || null);
        const gly = !isLowFat ? (recipeData.health_metric || recipeData.glycemic_info) : (recipeData.glycemic_info || null);

        await Api.saveFavorite({
          recipe_name: recipeName,
          category: recipeData.category || "custom",
          difficulty: recipeData.difficulty || "健康膳食",
          calories: cal,
          glycemic_info: gly,
          ingredients_needed: recipeData.ingredients_needed || [],
          pantry_staples: recipeData.pantry_staples || "",
          cooking_steps: recipeData.cooking_steps || [],
          chef_tips: recipeData.chef_tips || ""
        });
        isFav = true;
        renderStarUI();
        allFavoritesCache.push({ recipe_name: recipeName });
        alert("🎉 菜谱已成功存入您的收藏夹！");
      }
    } catch (err) {
      alert(err.message || "收藏操作失败");
    }
  };
}

// ==================== 8. 特殊营养健康定制 ====================
window.openSpecialRecipeModal = async () => {
  window.openModal("specialRecipeModal");
  window.switchSpecialType('custom_health');
  await loadCustomHealthMembersSelection();
  renderSubCuisinesAndMethods("special", document.getElementById("specialRecipeCuisineSelect")?.value || "chinese");
};

async function loadCustomHealthMembersSelection() {
  const container = document.getElementById("customHealthMembersPicker");
  if (!container) return;
  try {
    const list = await Api.getHealthProfiles();
    if (!list.length) {
      container.innerHTML = '<span class="text-xs text-slate-400">暂无成员画像，请先在右上角「健康状况」中填写！</span>';
      return;
    }
    container.innerHTML = list.map(m => `
      <label class="flex items-center gap-1.5 p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs cursor-pointer hover:bg-emerald-50/50">
        <input type="checkbox" value="${m.id}" onchange="autoUpdateCustomDinersCount()" class="custom-member-cb rounded text-emerald-600 focus:ring-emerald-500" checked />
        <span class="font-bold text-slate-800">${m.member_name}</span>
        <span class="text-[10px] text-rose-500">(${(m.conditions || []).join('、') || '正常'})</span>
      </label>
    `).join('');
    autoUpdateCustomDinersCount();
  } catch (e) {}
}

window.autoUpdateCustomDinersCount = function() {
  const checked = document.querySelectorAll('#customHealthMembersPicker input:checked');
  const countEl = document.getElementById("customHealthCalculatedPeople");
  if (countEl) countEl.textContent = `${checked.length} 人份 (自动锁定)`;
};

window.switchSpecialType = function(type) {
  currentSpecialType = type;
  const tabs = ['custom_health', 'low_fat', 'diabetic', 'gout', 'goiter'];
  tabs.forEach(t => {
    const btn = document.getElementById(`btnType_${t}`);
    if (btn) {
      if (t === type) {
        btn.className = "py-2.5 px-3 rounded-xl border font-bold text-xs border-emerald-500 bg-emerald-50 text-emerald-700 shadow-sm";
      } else {
        btn.className = "py-2.5 px-3 rounded-xl border font-bold text-xs border-slate-200 text-slate-600 hover:bg-slate-50";
      }
    }
  });

  const customPicker = document.getElementById("customHealthPickerSection");
  if (customPicker) {
    customPicker.classList.toggle("hidden", type !== 'custom_health');
  }
};

window.fetchSpecialRecipe = async function() {
  const container = document.getElementById("specialRecipeContent");
  const btn = document.querySelector("#specialRecipeModal button[onclick='fetchSpecialRecipe()']");

  if (btn) {
    btn.disabled = true;
    btn.classList.add("opacity-70", "cursor-not-allowed");
  }

  container.classList.remove("hidden");
  container.innerHTML = `
    <div class="py-6 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
      <svg class="animate-spin h-4 w-4 text-emerald-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
      <span>AI 正在研判专属指标、调和火候技法与烹饪时间并构思菜名...</span>
    </div>
  `;

  const cuisine = document.getElementById("specialRecipeCuisineSelect")?.value || "chinese";
  const subCuisine = document.getElementById("specialRecipeSubCuisineSelect")?.value || "";
  const cookingMethod = document.getElementById("specialRecipeCookingMethodSelect")?.value || "";
  const cookingTime = document.getElementById("specialRecipeCookingTimeSelect")?.value || "";
  const mealType = document.getElementById("specialRecipeMealTypeSelect")?.value || "dinner";

  try {
    let recipe;
    if (currentSpecialType === 'custom_health') {
      const checkedBoxes = document.querySelectorAll('#customHealthMembersPicker input:checked');
      const profileIds = Array.from(checkedBoxes).map(cb => parseInt(cb.value));
      if (!profileIds.length) {
        alert("请至少勾选一位家庭成员画像！");
        container.classList.add("hidden");
        return;
      }
      recipe = await Api.getCustomHealthRecipe({
        selected_profile_ids: profileIds,
        cuisine,
        sub_cuisine: subCuisine,
        cooking_method: cookingMethod,
        cooking_time: cookingTime,
        meal_type: mealType
      });
      recipe.category = 'custom_health';
    } else {
      const people = document.getElementById("specialPeopleCount")?.value || 2;
      recipe = await Api.getSpecialRecipe(currentSpecialType, people, {
        cuisine,
        sub_cuisine: subCuisine,
        cooking_method: cookingMethod,
        cooking_time: cookingTime,
        meal_type: mealType
      });
      recipe.category = currentSpecialType;
    }

    lastSpecialRecipe = recipe;

    let healthBadge = '';
    if (recipe.health_metric) {
      healthBadge = `<div class="bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold px-3 py-1.5 rounded-xl shadow-xs inline-flex items-center gap-1">${recipe.health_metric}</div>`;
    }

    const ingredientsHtml = (recipe.ingredients_needed || []).map(i => {
      const isPantry = i.from_pantry === true;
      const tag = isPantry
        ? `<span class="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">冰箱现存</span>`
        : `<div class="flex items-center gap-1.5">
             <span class="text-[10px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-bold">需采买</span>
             <button onclick="addSingleIngredientToShopping('${encodeURIComponent(i.name)}', '${encodeURIComponent(i.amount || '适量')}', '${encodeURIComponent(recipe.recipe_name)}')" class="px-2 py-0.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[10px] font-bold transition shadow-2xs">
               + 备菜
             </button>
           </div>`;
      return `<li class="flex items-center justify-between py-2 border-b border-slate-100 text-xs text-slate-700"><span>${i.name} (${i.amount || '适量'})</span> ${tag}</li>`;
    }).join('');

    let missingArr = recipe.missing_ingredients_to_buy || [];
    if (missingArr.length === 0 && Array.isArray(recipe.ingredients_needed)) {
      missingArr = recipe.ingredients_needed.filter(i => !i.from_pantry);
    }

    let missingBuySection = '';
    if (missingArr && missingArr.length > 0) {
      const missingList = missingArr.map(m => `${m.name} (${m.amount || '适量'})`).join('、');
      missingBuySection = `
        <div class="p-3.5 bg-amber-50 rounded-2xl border border-amber-200 mt-3 text-xs shadow-xs">
          <div class="flex items-center justify-between">
            <span class="font-bold text-amber-900 flex items-center gap-1.5"><span>🛒</span> 缺少食材 (${missingArr.length} 种)：</span>
            <button onclick="addMissingToShoppingList()" class="px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold transition shadow-sm">
              一键加购全部
            </button>
          </div>
          <p class="text-amber-800 mt-1.5 leading-relaxed">${missingList}</p>
        </div>
      `;
    }

    // 营养菜谱直接调用专属无参安全跳转 jumpSpecialRecipeToChat()
    container.innerHTML = `
      <div class="flex justify-between items-center pb-2.5 border-b border-slate-200">
        <div>
          <h4 class="font-bold text-slate-900 text-base">${recipe.recipe_name}</h4>
          <span class="text-[11px] text-slate-400 font-medium">${recipe.difficulty || '健康膳食'}</span>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" onclick="jumpSpecialRecipeToChat()" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition shadow-xs flex items-center gap-1">
            <span>🔍</span> <span>详细一点 · 大厨精讲</span>
          </button>
          <button id="btnSaveSpecialRecipeStar"></button>
        </div>
      </div>
      <div class="my-2.5 flex flex-wrap gap-2">${healthBadge}</div>
      ${recipe.diet_description ? `<div class="p-3 bg-slate-100/80 rounded-2xl border border-slate-200/80 text-xs text-slate-700 leading-relaxed mt-2.5"><span class="font-bold text-slate-900">💡 膳食机理：</span>${recipe.diet_description}</div>` : ''}
      ${missingBuySection}
      <div class="mt-3.5">
        <h5 class="text-xs font-bold text-slate-800 mb-1.5">主配食材清单：</h5>
        <ul class="bg-white rounded-2xl border border-slate-200 p-3 divide-y divide-slate-50">${ingredientsHtml}</ul>
      </div>
      <div class="mt-3 text-xs text-slate-600 bg-white p-3 rounded-2xl border border-slate-200">
        <span class="font-bold text-slate-800">烹饪调味建议：</span>${recipe.pantry_staples || '低油低盐'}
      </div>
      <div class="mt-3.5 text-xs text-slate-700">
        <span class="font-bold text-slate-800">烹饪步骤：</span>
        <ol class="list-decimal list-inside space-y-1 bg-white p-3.5 rounded-2xl border border-slate-200 leading-relaxed">
          ${(recipe.cooking_steps || []).map(s => `<li>${s}</li>`).join('')}
        </ol>
      </div>
      <div class="mt-4 pt-3 border-t border-slate-200 flex flex-col sm:flex-row gap-2">
        ${missingArr.length > 0 ? `
          <button onclick="addMissingToShoppingList()" class="flex-1 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-xl text-xs font-bold transition shadow-sm flex items-center justify-center gap-1.5">
            <span>🛒</span> <span>加入备菜清单 (${missingArr.length}种需买)</span>
          </button>
        ` : ''}
        <button onclick="triggerDeductForSpecial()" class="flex-1 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-sm flex items-center justify-center gap-1.5">
          <span>🍳</span> <span>做完这道菜，核对消耗并减碳</span>
        </button>
      </div>
    `;

    setupStarButton("btnSaveSpecialRecipeStar", recipe.recipe_name, recipe);

  } catch (err) {
    container.innerHTML = `<div class="text-red-500 text-xs text-center py-4">膳食定制响应异常: ${err.message}</div>`;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("opacity-70", "cursor-not-allowed");
    }
  }
};

window.addSingleIngredientToShopping = async function(encodedName, encodedAmount, encodedSourceRecipe) {
  const name = decodeURIComponent(encodedName).trim();
  const amount = decodeURIComponent(encodedAmount).trim() || '适量';
  const source_recipe = decodeURIComponent(encodedSourceRecipe).trim() || '健康定制菜谱';

  if (!name) return;

  try {
    const res = await Api.addShoppingBatch([{ name, amount, source_recipe }]);
    const data = await res.json();
    if (res.ok) {
      alert(`✅ 已将「${name}」放入您的备菜采购篮！`);
      await refreshShoppingBadge();
    } else {
      alert(`⚠️ 加购失败：${data.detail || "请检查网络"}`);
    }
  } catch (e) {
    alert("加入备菜清单网络异常");
  }
};

window.addMissingToShoppingList = async function() {
  if (!lastSpecialRecipe) return alert("暂无可加购的菜谱！");
  let rawList = lastSpecialRecipe.missing_ingredients_to_buy || [];
  if (rawList.length === 0 && Array.isArray(lastSpecialRecipe.ingredients_needed)) {
    rawList = lastSpecialRecipe.ingredients_needed.filter(i => !i.from_pantry);
  }

  if (!rawList.length) return alert("主配料冰箱中均有现存，无需额外加购！");

  const items = rawList.map(m => ({
    name: typeof m === 'string' ? m : (m.name || '食材'),
    amount: typeof m === 'string' ? '适量' : (m.amount || '适量'),
    source_recipe: lastSpecialRecipe.recipe_name
  })).filter(i => i.name.trim().length > 0);

  try {
    const res = await Api.addShoppingBatch(items);
    const data = await res.json();
    if (res.ok) {
      alert(`🎉 ${data.message}`);
      await refreshShoppingBadge();
    } else {
      alert(`⚠️ 加购失败：${data.detail || "请检查网络"}`);
    }
  } catch (err) {
    alert("网络异常，无法加入备菜清单");
  }
};

// ==================== 9. 今日吃啥双轨推荐 ====================
window.openTodayEatModal = () => {
  window.openModal("todayEatModal");
  renderSubCuisinesAndMethods("todayEat", document.getElementById("todayEatRecipeCuisineSelect")?.value || "chinese");
};

window.fetchTodayEatRecipes = async function() {
  const cards = document.getElementById("todayEatCards");
  const people = parseInt(document.getElementById("todayEatPeopleCount")?.value) || 2;
  const cuisine = document.getElementById("todayEatRecipeCuisineSelect")?.value || "chinese";
  const subCuisine = document.getElementById("todayEatRecipeSubCuisineSelect")?.value || "";
  const cookingMethod = document.getElementById("todayEatRecipeCookingMethodSelect")?.value || "";
  const cookingTime = document.getElementById("todayEatRecipeCookingTimeSelect")?.value || "";
  const mealType = document.getElementById("todayEatRecipeMealTypeSelect")?.value || "dinner";

  cards.classList.add("hidden");
  try {
    const data = await Api.getTodayWhatToEat(people, {
      cuisine,
      sub_cuisine: subCuisine,
      cooking_method: cookingMethod,
      cooking_time: cookingTime,
      meal_type: mealType
    });
    lastTodayEatData = data;

    const A = data.recipe_1_in_pantry;
    A.category = 'today_pantry';
    document.getElementById("recipeAName").innerText = A.recipe_name;
    document.getElementById("recipeADesc").innerText = A.description || "冰箱现有食材直接烹饪";
    document.getElementById("recipeAIngredients").innerHTML = (A.ingredients_needed || []).map(i => `<li>${i.name} : ${i.amount}</li>`).join("");
    document.getElementById("recipeASteps").innerHTML = (A.cooking_steps || []).map(s => `<li>${s}</li>`).join("");

    const B = data.recipe_2_need_shopping;
    B.category = 'today_shopping';
    document.getElementById("recipeBName").innerText = B.recipe_name;
    document.getElementById("recipeBDesc").innerText = B.description || "新尝鲜菜谱";
    document.getElementById("recipeBMissing").innerHTML = (B.missing_ingredients_to_buy || []).map(i => `<li>${i.name} (${i.amount})</li>`).join("");
    document.getElementById("recipeBSteps").innerHTML = (B.cooking_steps || []).map(s => `<li>${s}</li>`).join("");

    setupStarButton("btnSavePlanAStar", A.recipe_name, A);
    setupStarButton("btnSavePlanBStar", B.recipe_name, B);
    cards.classList.remove("hidden");
  } catch (err) {
    alert("今日双菜谱规划异常: " + err.message);
  }
};

window.addRecipeBToShoppingList = async function() {
  if (!lastTodayEatData?.recipe_2_need_shopping) return alert("暂无尝鲜菜谱！");
  const B = lastTodayEatData.recipe_2_need_shopping;
  let rawList = B.missing_ingredients_to_buy || [];
  if (rawList.length === 0 && Array.isArray(B.ingredients_needed)) {
    rawList = B.ingredients_needed.filter(i => !i.from_pantry);
  }

  const items = rawList.map(m => ({
    name: typeof m === 'string' ? m : (m.name || '食材'),
    amount: typeof m === 'string' ? '适量' : (m.amount || '适量'),
    source_recipe: B.recipe_name
  })).filter(i => i.name.trim().length > 0);

  try {
    const res = await Api.addShoppingBatch(items);
    const data = await res.json();
    if (res.ok) {
      alert(`🎉 ${data.message}`);
      await refreshShoppingBadge();
    } else {
      alert("加购失败");
    }
  } catch (err) {
    alert("加购失败");
  }
};

// ==================== 10. AI 厨房对话管家专属跳转与长记忆调度 ====================

// 恢复本地存储的历史对话
function restoreChatMemory() {
  try {
    const saved = sessionStorage.getItem(CHAT_STORAGE_KEY);
    if (saved) {
      chatHistory = JSON.parse(saved);
      const container = document.getElementById("chatMessagesStream");
      if (container && chatHistory.length > 0) {
        container.innerHTML = "";
        chatHistory.forEach(m => {
          appendChatMessage(m.role, m.content, false);
        });
      }
    }
  } catch (e) {
    console.warn("恢复聊天记忆失败:", e);
  }
}

// 【彻底清空 AI 的记忆与上下文指针】
window.clearChatHistoryMemory = function() {
  if (!confirm("确定彻底清空 AI 的所有历史对话与前序记忆吗？")) return;
  chatHistory = [];
  currentChatRecipeContext = null;
  returnTargetScope = null;

  sessionStorage.removeItem(CHAT_STORAGE_KEY);
  sessionStorage.removeItem(CHAT_SUMMARY_KEY);
  localStorage.removeItem(CHAT_STORAGE_KEY);
  localStorage.removeItem(CHAT_SUMMARY_KEY);

  const banner = document.getElementById("chatContextBanner");
  if (banner) banner.classList.add("hidden");

  const container = document.getElementById("chatMessagesStream");
  if (container) {
    container.innerHTML = `
      <div class="flex justify-start gap-3">
        <div class="flex items-start gap-2.5 max-w-[85%]">
          <div class="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center text-sm shrink-0 shadow-2xs">
            👨‍🍳
          </div>
          <div class="p-3.5 bg-white border border-slate-200 rounded-2xl rounded-tl-xs shadow-2xs text-xs text-slate-800 leading-relaxed">
            记忆已全部清空重置。请问有什么新的美食或厨房需求我可以协助您吗？
          </div>
        </div>
      </div>
    `;
  }
};

// 【核心通用跳转底层】：关闭所有模态框，0 秒立即切换至 AI 大页
window.jumpToDetailedRecipeChat = function(recipeName, recipeData, sourceScope) {
  currentChatRecipeContext = recipeData;
  returnTargetScope = sourceScope;

  // 1. 关闭所有可能弹出的浮窗
  document.querySelectorAll('.fixed.inset-0').forEach(el => {
    if (el.id !== 'authModal') el.classList.add('hidden');
  });

  // 2. 立即切换到 chat 独立大页视图
  window.switchMainView('chat');

  // 3. 展现顶部来源横幅
  const banner = document.getElementById("chatContextBanner");
  const bannerTitle = document.getElementById("chatContextRecipeTitle");
  if (banner && bannerTitle) {
    bannerTitle.textContent = `《${recipeName}》`;
    banner.classList.remove("hidden");
  }

  // 4. 自动聚焦输入框并触发一次精讲 Prompt
  const promptText = `请针对菜品《${recipeName}》展开五星级大厨级保姆式教学：1. 食材精确刀工与腌制抓匀手法；2. 油温气泡判断与火候转换；3. 精确到分钟的下锅翻炒节奏；4. 常见翻车救场技巧！`;
  sendUserChatMessage(promptText);
};

// 【专供：今日吃啥方案 A 跳转】
window.jumpTodayEatPlanAToChat = function() {
  if (!lastTodayEatData || !lastTodayEatData.recipe_1_in_pantry) {
    return alert("今日吃啥菜谱尚未生成，请先生成方案！");
  }
  const r = lastTodayEatData.recipe_1_in_pantry;
  window.jumpToDetailedRecipeChat(r.recipe_name, r, 'todayEat');
};

// 【专供：今日吃啥方案 B 跳转】
window.jumpTodayEatPlanBToChat = function() {
  if (!lastTodayEatData || !lastTodayEatData.recipe_2_need_shopping) {
    return alert("今日吃啥尝鲜菜谱尚未生成，请先生成方案！");
  }
  const r = lastTodayEatData.recipe_2_need_shopping;
  window.jumpToDetailedRecipeChat(r.recipe_name, r, 'todayEat');
};

// 【专供：营养健康定制跳转】
window.jumpSpecialRecipeToChat = function() {
  if (!lastSpecialRecipe) {
    return alert("请先生成营养健康定制菜谱！");
  }
  window.jumpToDetailedRecipeChat(lastSpecialRecipe.recipe_name, lastSpecialRecipe, 'special');
};

// 【专供：收藏夹安全按 ID 跳转】
window.jumpFavoriteToChatById = function(favId) {
  const fav = allFavoritesCache.find(f => f.id === favId);
  if (!fav) {
    return alert("未找到该收藏菜谱缓存，请重试！");
  }
  window.jumpToDetailedRecipeChat(fav.recipe_name, fav, 'favorites');
};

// 【专供：社区帖子详情菜谱跳转】
window.jumpCommunityPostToChat = function() {
  const pid = parseInt(document.getElementById("activeDetailCommentPostId")?.value);
  const post = currentCommunityPosts.find(p => p.id === pid);
  if (post && post.recipe_data) {
    window.jumpToDetailedRecipeChat(post.recipe_data.recipe_name || post.title, post.recipe_data, 'community');
  } else {
    alert("该动态未关联菜谱！");
  }
};

window.returnFromDetailedRecipeChat = function() {
  const target = returnTargetScope;
  returnTargetScope = null;
  currentChatRecipeContext = null;

  const banner = document.getElementById("chatContextBanner");
  if (banner) banner.classList.add("hidden");

  window.switchMainView('fridge');

  if (target === 'pantry' && currentActiveItem) {
    window.openModal('foodDetailModal');
  } else if (target === 'special') {
    window.openModal('specialRecipeModal');
  } else if (target === 'todayEat') {
    window.openModal('todayEatModal');
  } else if (target === 'favorites') {
    window.openModal('favoritesModal');
  }
};

window.sendUserChatMessage = async function(forcedMessage = null) {
  const inputEl = document.getElementById("chatUserInput");
  const text = (forcedMessage || inputEl?.value || "").trim();
  if (!text) return;

  if (!forcedMessage && inputEl) {
    inputEl.value = "";
  }

  // 请求历史必须只包含当前问题之前的消息。
  const historyForRequest = chatHistory.slice(-12);

  // 1. 渲染用户问题气泡
  appendChatMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  // 2. 显示大厨思考动画
  const loadingBubbleId = appendChatLoadingBubble();

  try {
    const currentSummary = sessionStorage.getItem(CHAT_SUMMARY_KEY) || "";

    const payload = {
      message: text,
      history: historyForRequest,
      recipe_context: currentChatRecipeContext,
      memory_summary: currentSummary
    };

    const res = await Api.chatKitchenAssistant(payload);
    removeChatBubble(loadingBubbleId);

    // 健壮性保障：如果回复文本为空，自动填充合理答复，彻底杜绝空白气泡
    let finalReply = (res.reply || "").trim();
    if (!finalReply) {
      if (res.is_refused) {
        finalReply = "抱歉呀，此对话并非智鲜大厨的智能服务范围。作为专属厨房管家，我只专注于食材保鲜、双门冰箱温区管理与烹饪菜谱相关咨询。请问有什么厨房需求我可以协助您吗？";
      } else {
        finalReply = "好的，我已经为您记录并调整了操作！还有什么食材或烹饪问题需要协助吗？";
      }
    }

    // 3. 渲染大厨回复气泡
    appendChatMessage('assistant', finalReply, res.is_refused);
    chatHistory.push({ role: 'assistant', content: finalReply });

    if (chatHistory.length > 30) {
      chatHistory = chatHistory.slice(-30);
    }
    sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatHistory));

    // 4. 双向调度联动刷新：AI 入库/挪动冰箱食材或备菜时，自动刷新冰箱 3D 界面和角标！
    if (res.actions_executed && res.actions_executed.length > 0) {
      await refreshShoppingBadge();
      await loadPantryItems();
    }
  } catch (err) {
    removeChatBubble(loadingBubbleId);
    appendChatMessage('assistant', `抱歉，大厨与厨房服务器连接中断，请检查网络后重试。(提示: ${err.message || '网络连接超时'})`, true);
  }
};

function appendChatMessage(role, content, isWarning = false) {
  const container = document.getElementById("chatMessagesStream");
  if (!container) return;

  // 终极保护：如果内容为空则不渲染空标签
  const textContent = (content || "").trim();
  if (!textContent) return;

  const bubbleWrapper = document.createElement("div");
  bubbleWrapper.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} gap-3 animate-in fade-in duration-200`;

  let avatar = role === 'user' ? '👤' : '👨‍🍳';
  let bgClass = role === 'user'
    ? 'bg-emerald-600 text-white rounded-tr-xs'
    : (isWarning ? 'bg-amber-50 border border-amber-200 text-amber-900 rounded-tl-xs' : 'bg-white border border-slate-200 text-slate-800 rounded-tl-xs');

  const formattedContent = textContent.replace(/\n/g, '<br/>');

  bubbleWrapper.innerHTML = `
    <div class="flex items-start gap-2.5 max-w-[85%] ${role === 'user' ? 'flex-row-reverse' : 'flex-row'}">
      <div class="w-8 h-8 rounded-full ${role === 'user' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-800'} flex items-center justify-center text-sm shrink-0 border border-slate-200 shadow-2xs">
        ${avatar}
      </div>
      <div class="p-3.5 rounded-2xl shadow-2xs text-xs leading-relaxed ${bgClass}">
        ${formattedContent}
      </div>
    </div>
  `;

  container.appendChild(bubbleWrapper);
  scrollChatToBottom();
}

function appendChatLoadingBubble() {
  const container = document.getElementById("chatMessagesStream");
  if (!container) return null;

  const id = `loading_${Date.now()}`;
  const wrapper = document.createElement("div");
  wrapper.id = id;
  wrapper.className = "flex justify-start gap-3 animate-pulse";
  wrapper.innerHTML = `
    <div class="flex items-start gap-2.5">
      <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-sm shrink-0 border border-slate-200">
        👨‍🍳
      </div>
      <div class="p-3.5 bg-white border border-slate-200 rounded-2xl rounded-tl-xs text-xs text-slate-400 flex items-center gap-1.5 shadow-2xs">
        <svg class="animate-spin h-3.5 w-3.5 text-emerald-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
        <span>大厨正在精细推演火候与烹饪方案...</span>
      </div>
    </div>
  `;
  container.appendChild(wrapper);
  scrollChatToBottom();
  return id;
}

function removeChatBubble(id) {
  if (!id) return;
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollChatToBottom() {
  const container = document.getElementById("chatMessagesStream");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}

window.sendQuickChatPrompt = function(promptText) {
  sendUserChatMessage(promptText);
};

// ==================== 11. 备菜清单 ====================
window.openShoppingListModal = async function() {
  window.openModal("shoppingListModal");
  await refreshShoppingList();
};

async function refreshShoppingList() {
  const items = await Api.getShoppingItems();
  const container = document.getElementById("shoppingItemsContainer");
  container.innerHTML = "";

  if (!items || items.length === 0) {
    container.innerHTML = '<div class="text-center py-8 text-xs text-slate-400">采购篮是空的</div>';
    document.getElementById("shoppingBadge").innerText = "0";
    return;
  }

  document.getElementById("shoppingBadge").innerText = items.length;

  items.forEach(item => {
    const div = document.createElement("div");
    div.className = "flex justify-between items-center p-3 bg-white border border-slate-200 rounded-xl shadow-sm";
    div.innerHTML = `
      <div>
        <span class="font-bold text-slate-800 text-sm">${item.name}</span>
        <span class="text-xs text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded ml-2 font-semibold">${item.amount || '适量'}</span>
        <p class="text-[11px] text-slate-400 mt-0.5">来源: ${item.source_recipe || '自主添加'}</p>
      </div>
      <button onclick="removeShoppingItem(${item.id})" class="px-2.5 py-1 bg-white hover:bg-red-50 text-red-600 border border-slate-200 rounded-lg text-xs font-semibold shadow-sm transition">
        ✓ 买到了 / 删除
      </button>
    `;
    container.appendChild(div);
  });
}

window.removeShoppingItem = async function(id) {
  await Api.deleteShoppingItem(id);
  await refreshShoppingList();
  await refreshShoppingBadge();
};

async function refreshShoppingBadge() {
  try {
    const items = await Api.getShoppingItems();
    const b = document.getElementById("shoppingBadge");
    if (b) b.innerText = items.length;
  } catch (e) {}
}

// ==================== 12. 食材扣减与批量核算 ====================
window.confirmDeductStock = async function() {
  if (!currentActiveItem) return;
  const used = parseFloat(document.getElementById("usedWeightInput").value);
  const currentUnit = currentActiveItem.unit || "克";

  if (isNaN(used) || used <= 0 || used > currentActiveItem.remaining_weight) {
    return alert(`请输入合法消耗克重 (不可超库存 ${currentActiveItem.remaining_weight}${currentUnit})！`);
  }

  const res = await Api.deductStock(currentActiveItem.id, used, "单项消耗");
  if (res.ok) {
    const data = await res.json();
    let carbonMsg = data.carbon_saved_grams ? `\n🌱 [AI 减碳] 本次减少食物碳损耗约 ${data.carbon_saved_grams}g CO2e` : "";
    alert(`✅ ${data.message}${carbonMsg}`);
    window.closeModal("foodDetailModal");
    await loadPantryItems();
  } else {
    alert("扣减失败");
  }
};

function isIngredientMatch(pantryName, recipeIngName) {
  const p = pantryName.trim().toLowerCase();
  const r = recipeIngName.trim().toLowerCase();
  if (p === r || p.includes(r) || r.includes(p)) return true;
  const cleanP = p.replace(/^(新鲜|精选|有机|手作|特级|野生|鲜嫩)/, '');
  const cleanR = r.replace(/^(新鲜|精选|有机|手作|特级|野生|鲜嫩)/, '');
  return cleanP.includes(cleanR) || cleanR.includes(cleanP);
}

function parseSuggestedAmount(amountStr, currentRemaining) {
  if (!amountStr) return Math.min(100, currentRemaining);
  const match = amountStr.match(/(\d+(\.\d+)?)/);
  if (match) {
    const num = parseFloat(match[1]);
    if (!isNaN(num) && num > 0) return Math.min(num, currentRemaining);
  }
  return Math.min(100, currentRemaining);
}

window.checkAndPromptIngredientsDeduct = async function(recipeName, ingredientsNeeded) {
  pendingRecipeName = recipeName || "定制佳肴";
  const currentPantry = await Api.getPantryItems();
  const matched = [];

  for (const ing of ingredientsNeeded || []) {
    const name = (typeof ing === 'string' ? ing : ing.name || "").trim();
    if (!name) continue;

    const found = currentPantry.find(p => !p.is_expired && isIngredientMatch(p.name, name));
    if (found && !matched.some(m => m.item_id === found.id)) {
      const rawAmount = typeof ing === 'object' ? ing.amount : "";
      const suggested = parseSuggestedAmount(rawAmount, found.remaining_weight);
      matched.push({
        item_id: found.id,
        name: found.name,
        remaining_weight: found.remaining_weight,
        unit: found.unit,
        suggested: Math.round(suggested * 10) / 10
      });
    }
  }

  if (matched.length === 0) return alert("检测到该菜谱在库食材无剩余或已耗尽，无需扣减！");

  pendingBatchItems = matched;
  const listContainer = document.getElementById("batchDeductList");
  listContainer.innerHTML = matched.map((m, idx) => `
    <div class="p-3 bg-slate-50 border border-slate-200 rounded-2xl flex items-center justify-between">
      <div>
        <h5 class="font-bold text-xs text-slate-800">${m.name}</h5>
        <span class="text-[11px] text-slate-400">剩余: <strong class="text-emerald-600">${m.remaining_weight} ${m.unit}</strong></span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="text-xs text-slate-500 font-medium">消耗:</span>
        <input type="number" step="any" min="0.1" max="${m.remaining_weight}" id="batchDeductInput_${idx}" value="${m.suggested}"
          class="w-20 px-2 py-1 bg-white border border-slate-300 rounded-lg text-xs font-bold text-slate-800 text-center focus:ring-2 focus:ring-cyan-500 outline-none"
        />
        <span class="text-xs font-semibold text-slate-600">${m.unit}</span>
      </div>
    </div>
  `).join('');

  window.openModal("batchDeductModal");
};

window.triggerDeductForPlanA = function() {
  if (!lastTodayEatData?.recipe_1_in_pantry) return alert("暂无可核算的菜谱！");
  const A = lastTodayEatData.recipe_1_in_pantry;
  window.checkAndPromptIngredientsDeduct(A.recipe_name, A.ingredients_needed);
};

window.triggerDeductForSpecial = function() {
  if (!lastSpecialRecipe) return alert("暂无可核算的特殊菜谱！");
  window.checkAndPromptIngredientsDeduct(lastSpecialRecipe.recipe_name, lastSpecialRecipe.ingredients_needed);
};

window.confirmBatchDeduct = async function() {
  const deductPayload = [];
  for (let i = 0; i < pendingBatchItems.length; i++) {
    const item = pendingBatchItems[i];
    const inputEl = document.getElementById(`batchDeductInput_${i}`);
    const val = parseFloat(inputEl.value);

    if (isNaN(val) || val <= 0 || val > item.remaining_weight) {
      alert(`食材「${item.name}」扣减值非法或超库存！`);
      inputEl.focus();
      return;
    }
    deductPayload.push({ item_id: item.item_id, deduct_weight: val });
  }

  try {
    const res = await Api.batchDeductStock(pendingRecipeName, deductPayload);
    const data = await res.json();
    if (res.ok) {
      let carbonMsg = data.total_carbon_saved_grams ? `\n🌱 [AI 减碳] 本道菜共避免碳排放约 ${data.total_carbon_saved_grams}g CO2e！` : "";
      alert(`✅ ${data.message}${carbonMsg}`);
      window.closeModal("batchDeductModal");
      window.closeModal("foodDetailModal");
      window.closeModal("specialRecipeModal");
      window.closeModal("todayEatModal");
      await loadPantryItems();
    } else {
      alert(parseErrorMessage(data));
    }
  } catch (err) {
    alert("扣减请求异常");
  }
};

// ==================== 13. 减碳周榜 ====================
window.loadCarbonLeaderboard = async function() {
  const containers = [
    document.getElementById("vegetarianLeaderboardContainer"),
    document.getElementById("nonVegetarianLeaderboardContainer")
  ].filter(Boolean);
  if (!containers.length) return;
  containers.forEach(container => {
    container.innerHTML = '<div class="text-xs text-slate-400 py-10 text-center">正在同步减碳榜单与生态账本...</div>';
  });

  try {
    const data = await Api.getCarbonLeaderboard();
    const cycleEl = document.getElementById("carbonCycleDesc");
    if (cycleEl) cycleEl.textContent = data.cycle_info.status;

    const renderBoard = (board, prefix, containerId) => {
      const container = document.getElementById(containerId);
      if (!container || !board) return;
      const my = board.my_stat || {};
      const rankEl = document.getElementById(`my${prefix}RankText`);
      const kgEl = document.getElementById(`my${prefix}KgText`);
      const treeEl = document.getElementById(`my${prefix}TreesText`);
      if (rankEl) rankEl.textContent = my.rank ?? "未上榜";
      if (kgEl) kgEl.textContent = `${my.carbon_saved_kg || 0} kg`;
      if (treeEl) treeEl.textContent = `${my.tree_days || 0} 天`;
      if (!board.top20 || !board.top20.length) {
        container.innerHTML = '<div class="text-xs text-slate-400 py-12 text-center">本周暂无记录，快做道菜积累减碳贡献吧！</div>';
        return;
      }
      container.innerHTML = board.top20.map(item => `
      <div class="flex items-center justify-between p-3.5 rounded-2xl ${item.is_me ? 'bg-emerald-50 border border-emerald-300 shadow-xs' : 'bg-slate-50 border border-slate-100'} text-xs">
        <div class="flex items-center gap-3.5">
          <span class="w-8 text-center font-black ${item.rank === 1 ? 'text-amber-500 text-base' : (item.rank === 2 ? 'text-slate-400 text-base' : (item.rank === 3 ? 'text-amber-700 text-base' : 'text-slate-400'))}">${item.rank}</span>
          <div>
            <span class="font-bold text-slate-800 text-sm">${item.username} ${item.is_me ? '<span class="text-[10px] text-emerald-600 font-bold px-1.5 py-0.5 bg-white rounded border border-emerald-200">(我)</span>' : ''}</span>
            <span class="text-[11px] text-slate-400 block mt-0.5">本周烹饪利用 ${item.cook_times} 次</span>
          </div>
        </div>
        <div class="text-right">
          <span class="font-bold text-emerald-600 font-mono text-sm">${item.carbon_saved_kg} kg CO2e</span>
          <span class="text-[11px] text-slate-400 block mt-0.5">≈ 植树 ${item.tree_days} 天</span>
        </div>
      </div>
      `).join('');
    };

    renderBoard(data.vegetarian, "Vegetarian", "vegetarianLeaderboardContainer");
    renderBoard(data.non_vegetarian, "NonVegetarian", "nonVegetarianLeaderboardContainer");
  } catch (err) {
    containers.forEach(container => {
      container.innerHTML = `<div class="text-xs text-red-500 py-6 text-center">${err.message}</div>`;
    });
  }
};

// ==================== 14. 美食社区 ====================
window.loadCommunityFeed = async function() {
  const container = document.getElementById("communityPostsContainer");
  if (!container) return;
  container.innerHTML = '<div class="text-xs text-slate-400 py-12 text-center col-span-full">加载食友动态中...</div>';

  try {
    currentCommunityPosts = await Api.getCommunityPosts(communityPage, 20);
    if (!currentCommunityPosts.length) {
      container.innerHTML = '<div class="text-xs text-slate-400 py-16 text-center col-span-full">广场空空如也，点击右上角发布您的第一篇美食大作！</div>';
      return;
    }

    container.innerHTML = currentCommunityPosts.map(p => `
      <div class="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-2xs flex flex-col justify-between cursor-pointer hover:border-emerald-300 transition" onclick="openPostDetailModal(${p.id})">
        <div>
          <img src="${p.image_url}" alt="${p.title}" class="w-full h-48 object-cover" />
          <div class="p-4">
            <div class="flex justify-between items-center text-[11px] text-slate-400">
              <span class="font-bold text-slate-700 text-xs">${p.author_name}</span>
              <span>${p.created_at}</span>
            </div>
            <h4 class="font-bold text-sm text-slate-900 mt-1.5">${p.title}</h4>
            <p class="text-xs text-slate-600 mt-1 line-clamp-2 leading-relaxed">${p.content}</p>
            ${p.has_recipe ? '<span class="inline-block mt-2.5 text-[10px] px-2.5 py-0.5 rounded-md bg-emerald-50 text-emerald-700 font-bold border border-emerald-200">附带可复刻菜谱</span>' : ''}
          </div>
        </div>
        <div class="p-4 pt-0 flex justify-between items-center text-xs text-slate-500 border-t border-slate-100" onclick="event.stopPropagation()">
          <button onclick="togglePostLike(${p.id})" class="flex items-center gap-1.5 hover:text-rose-500 transition">
            <span class="${p.is_liked ? 'text-rose-500 font-bold' : 'text-slate-400'}">♥</span>
            <span>${p.likes_count}</span>
          </button>
          <button onclick="openPostDetailModal(${p.id})" class="flex items-center gap-1.5 hover:text-blue-500">
            <span>💬</span>
            <span>${p.comment_count}</span>
          </button>
          ${!p.is_author ? `
            <button onclick="openReportPostModal(${p.id})" class="text-[10px] text-slate-400 hover:text-red-500">
              举报
            </button>
          ` : ''}
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="text-xs text-red-500 py-6 text-center col-span-full">${err.message}</div>`;
  }
};

window.togglePostLike = async function(postId) {
  try {
    const res = await Api.togglePostLike(postId);
    const p = currentCommunityPosts.find(item => item.id === postId);
    if (p) {
      p.is_liked = res.is_liked;
      p.likes_count = res.likes_count;
      loadCommunityFeed();
    }
  } catch (e) {}
};

window.openCreatePostModal = () => {
  window.clearCommunityPostImage();
  window.openModal("createCommunityPostModal");
};

window.handleCommunityImageSelect = function(e) {
  const file = e.target.files[0];
  const previewBox = document.getElementById("communityImagePreviewBox");
  const previewImg = document.getElementById("foodImagePreviewImg");
  if (file && previewBox && previewImg) {
    const reader = new FileReader();
    reader.onload = (evt) => {
      previewImg.src = evt.target.result;
      previewBox.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
  }
};

window.clearCommunityPostImage = function() {
  const fileInput = document.getElementById("postImageInput");
  if (fileInput) fileInput.value = "";
  const previewBox = document.getElementById("communityImagePreviewBox");
  if (previewBox) previewBox.classList.add("hidden");
};

window.submitCommunityPost = async function(e) {
  e.preventDefault();
  const title = document.getElementById("postTitleInput").value.trim();
  const content = document.getElementById("postContentInput").value.trim();
  const fileInput = document.getElementById("postImageInput");

  if (!title || !content || !fileInput.files.length) {
    return alert("请填写菜品名、心得并上传照片！");
  }

  const btn = document.getElementById("btnSubmitPost");
  if (btn) btn.disabled = true;

  try {
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    const uploadRes = await Api.uploadCommunityImage(fd);

    await Api.createCommunityPost({
      title,
      content,
      image_url: uploadRes.image_url,
      recipe_data: lastGeneratedRecipe || lastSpecialRecipe || null
    });

    alert("🎉 美食打卡成功发布！");
    window.closeModal("createCommunityPostModal");
    window.clearCommunityPostImage();
    document.getElementById("postTitleInput").value = "";
    document.getElementById("postContentInput").value = "";
    await loadCommunityFeed();
  } catch (err) {
    alert("发布失败: " + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
};

// 社区详情中的“详细一点”安全直接跳转
window.openPostDetailModal = async function(postId) {
  window.openModal("postDetailModal");
  const container = document.getElementById("postDetailContentContainer");
  container.innerHTML = `<div class="text-center py-8 text-xs text-slate-400">正在获取打卡详情...</div>`;

  try {
    const post = await Api.getCommunityPostDetail(postId);
    const r = post.recipe_data;

    let recipeSection = '';
    if (r && r.recipe_name) {
      const ingList = (r.ingredients_needed || []).map(i => {
        const name = typeof i === 'string' ? i : i.name;
        const amount = typeof i === 'string' ? '' : (i.amount ? `(${i.amount})` : '');
        return `${name}${amount}`;
      }).join('、');

      recipeSection = `
        <div class="mt-4 p-4 bg-emerald-50/60 rounded-2xl border border-emerald-200 space-y-2">
          <div class="flex justify-between items-center">
            <span class="font-bold text-xs text-emerald-900 flex items-center gap-1">
              <span>📖</span> 关联菜谱：${r.recipe_name || post.title}
            </span>
            <div class="flex items-center gap-2">
              <button type="button" onclick="jumpCommunityPostToChat()" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition shadow-2xs">
                详细一点
              </button>
              <button id="btnSavePostDetailRecipeStar"></button>
            </div>
          </div>
          <p class="text-xs text-slate-600"><strong class="text-slate-700">食材搭配：</strong>${ingList || '常规搭配'}</p>
          ${r.cooking_steps ? `
            <div class="text-xs text-slate-600">
              <strong class="text-slate-700">做法简析：</strong>
              <ol class="list-decimal list-inside space-y-0.5 mt-1 text-[11px] text-slate-500">
                ${r.cooking_steps.map(s => `<li>${s}</li>`).join('')}
              </ol>
            </div>
          ` : ''}
        </div>
      `;
    }

    container.innerHTML = `
      <div class="space-y-3">
        <div class="flex justify-between items-center pb-2 border-b border-slate-100">
          <div>
            <span class="font-bold text-slate-900 text-sm flex items-center gap-1.5">
              <span>👨‍🍳</span> <span>${post.author_name}</span>
              ${post.is_author ? '<span class="text-[10px] px-1.5 py-0.5 bg-emerald-100 text-emerald-700 font-bold rounded">我发布的</span>' : ''}
            </span>
            <span class="text-[10px] text-slate-400 block mt-0.5">发布时间：${post.created_at}</span>
          </div>
          ${post.is_author ? `
            <button onclick="deleteMyCommunityPost(${post.id})" class="px-3 py-1 bg-rose-50 text-rose-600 border border-rose-200 rounded-xl text-xs font-bold hover:bg-rose-100 transition">
              🗑️ 删除动态
            </button>
          ` : `
            <button onclick="openReportPostModal(${post.id})" class="px-2.5 py-1 bg-slate-100 text-slate-500 rounded-xl text-xs hover:text-rose-600 transition">
              ⚠️ 举报
            </button>
          `}
        </div>

        <div class="rounded-2xl overflow-hidden border border-slate-100 bg-slate-50">
          <img src="${post.image_url}" class="w-full max-h-72 object-cover" />
        </div>

        <div>
          <h4 class="font-bold text-base text-slate-900">${post.title}</h4>
          <p class="text-xs text-slate-700 mt-1.5 leading-relaxed whitespace-pre-wrap">${post.content}</p>
        </div>

        ${recipeSection}
      </div>
    `;

    if (r && r.recipe_name) {
      setupStarButton("btnSavePostDetailRecipeStar", r.recipe_name || post.title, r);
    }

    document.getElementById("activeDetailCommentPostId").value = post.id;
    await refreshDetailCommentsList(post.id);

  } catch (err) {
    container.innerHTML = `<div class="text-center py-6 text-xs text-rose-500">${err.message}</div>`;
  }
};

window.deleteMyCommunityPost = async function(postId) {
  if (!confirm("确定删除这条美食打卡动态吗？删除后动态及评论将移除，但其他食友已收藏的菜谱不会受任何影响。")) return;
  try {
    const res = await Api.deleteCommunityPost(postId);
    alert(res.message);
    window.closeModal("postDetailModal");
    await loadCommunityFeed();
  } catch (err) {
    alert(err.message || "删除动态失败");
  }
};

window.deleteTargetComment = async function(commentId, postId) {
  if (!confirm("确定删除这条评论吗？")) return;
  try {
    const res = await Api.deleteCommunityComment(commentId);
    alert(res.message);
    await refreshDetailCommentsList(postId);
    await loadCommunityFeed();
  } catch (err) {
    alert(err.message || "删除评论失败");
  }
};

async function refreshDetailCommentsList(postId) {
  const container = document.getElementById("postDetailCommentsContainer");
  container.innerHTML = '<div class="text-xs text-slate-400 py-2 text-center">加载留言中...</div>';
  try {
    const list = await Api.getPostComments(postId);
    if (!list.length) {
      container.innerHTML = '<div class="text-xs text-slate-400 py-2 text-center">暂无留言，快来抢沙发！</div>';
      return;
    }
    container.innerHTML = list.map(c => `
      <div class="p-2 bg-slate-50 rounded-xl text-xs flex justify-between items-start">
        <div class="flex-1 pr-2">
          <div class="flex items-center gap-1.5 font-bold text-slate-700">
            <span>${c.author_name}</span>
            <span class="text-[10px] text-slate-400 font-normal">${c.created_at}</span>
          </div>
          <p class="text-slate-600 mt-0.5">${c.content}</p>
        </div>
        ${c.can_delete ? `
          <button onclick="deleteTargetComment(${c.id}, ${postId})" class="text-[11px] text-rose-500 hover:text-rose-700 font-medium shrink-0">
            删除
          </button>
        ` : ''}
      </div>
    `).join('');
  } catch (e) {
    container.innerHTML = '<div class="text-xs text-rose-500 py-1 text-center">评论加载失败</div>';
  }
}

window.submitDetailNewComment = async function(e) {
  e.preventDefault();
  const postId = parseInt(document.getElementById("activeDetailCommentPostId").value);
  const input = document.getElementById("newDetailCommentText");
  const content = input.value.trim();
  if (!content) return;

  try {
    await Api.addPostComment(postId, content);
    input.value = "";
    await refreshDetailCommentsList(postId);
    await loadCommunityFeed();
  } catch (err) {
    alert(err.message || "发表失败");
  }
};

window.openReportPostModal = function(postId) {
  document.getElementById("reportTargetPostId").value = postId;
  window.openModal("reportPostModal");
};

window.submitPostReport = async function(e) {
  e.preventDefault();
  const postId = parseInt(document.getElementById("reportTargetPostId").value);
  const reason = document.getElementById("reportReasonSelect").value;
  const detail = document.getElementById("reportDetailInput").value.trim();

  try {
    const res = await Api.reportCommunityPost(postId, { reason, detail });
    alert("✅ " + res.message);
    window.closeModal("reportPostModal");
  } catch (err) {
    alert("举报提交失败: " + err.message);
  }
};

// ==================== 15. 收藏夹 (安全按 ID 跳转，绝无语法错误) ====================
window.openFavoritesModal = async function() {
  window.openModal("favoritesModal");
  const container = document.getElementById("favoritesContainer");
  const searchInput = document.getElementById("favoriteSearchInput");
  if (searchInput) searchInput.value = "";

  container.innerHTML = '<div class="text-center py-8 text-xs text-slate-400">正在查阅收藏宝典...</div>';

  try {
    allFavoritesCache = await Api.getFavorites();
    renderFavoritesList(allFavoritesCache);
  } catch (err) {
    container.innerHTML = '<div class="text-center py-8 text-xs text-red-400">获取失败</div>';
  }
};

function renderFavoritesList(list) {
  const container = document.getElementById("favoritesContainer");
  container.innerHTML = "";

  if (!list || list.length === 0) {
    container.innerHTML = '<div class="text-center py-10 text-xs text-slate-400">未找到匹配的菜谱</div>';
    return;
  }

  list.forEach(fav => {
    let ingredientsText = "";
    if (Array.isArray(fav.ingredients_needed)) {
      ingredientsText = fav.ingredients_needed.map(i => typeof i === 'string' ? i : i.name).filter(Boolean).join("、");
    }

    const div = document.createElement("div");
    div.className = "p-4 bg-white border border-slate-200 rounded-2xl space-y-2.5 shadow-xs transition hover:border-amber-300";
    div.innerHTML = `
      <div class="flex justify-between items-center">
        <div>
          <span class="font-bold text-slate-900 text-base">${fav.recipe_name}</span>
          <span class="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md ml-2 font-medium">${fav.difficulty || '健康美味'}</span>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" onclick="jumpFavoriteToChatById(${fav.id})" class="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition shadow-2xs">
            详细一点
          </button>
          <button onclick="deleteFavorite(${fav.id})" class="text-xs text-red-500 hover:text-red-700 font-semibold px-2 py-1 rounded hover:bg-red-50 transition">
            🗑️ 移除收藏
          </button>
        </div>
      </div>
      ${fav.calories ? `<div class="text-xs text-emerald-700 font-bold bg-emerald-50 px-2.5 py-1 rounded-lg w-fit">${fav.calories}</div>` : ''}
      ${fav.glycemic_info ? `<div class="text-xs text-cyan-700 font-bold bg-cyan-50 px-2.5 py-1 rounded-lg leading-relaxed">${fav.glycemic_info}</div>` : ''}
      ${ingredientsText ? `<div class="text-xs text-slate-600"><span class="font-semibold text-slate-700">主配食材：</span><span>${ingredientsText}</span></div>` : ''}
      <div class="text-xs text-slate-600">
        <span class="font-semibold text-slate-700">烹饪步骤：</span>
        <ol class="list-decimal list-inside space-y-0.5 mt-1 bg-slate-50 p-2.5 rounded-xl border border-slate-100">
          ${(fav.cooking_steps || []).map(s => `<li>${s}</li>`).join('')}
        </ol>
      </div>
    `;
    container.appendChild(div);
  });
}

window.filterFavorites = function(keyword) {
  const q = (keyword || "").trim().toLowerCase();
  if (!q) return renderFavoritesList(allFavoritesCache);
  const filtered = allFavoritesCache.filter(fav => (fav.recipe_name || "").toLowerCase().includes(q));
  renderFavoritesList(filtered);
};

window.deleteFavorite = async function(id) {
  if (!confirm("确定移除此菜谱收藏吗？")) return;
  await Api.deleteFavorite(id);
  allFavoritesCache = allFavoritesCache.filter(f => f.id !== id);
  renderFavoritesList(allFavoritesCache);
};

// ==================== 16. 初始化与事件监听 ====================
window.addEventListener('DOMContentLoaded', async () => {
  enableMiniAiDrag();
  document.getElementById('miniAiCloseBtn')?.addEventListener('click', () => document.getElementById('miniAiPanel')?.classList.add('hidden'));
  document.getElementById('miniAiSendBtn')?.addEventListener('click', () => sendMiniAiMessage());
  document.getElementById('miniAiInput')?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMiniAiMessage();
    }
  });
  window.addEventListener('pagehide', () => {
    sessionStorage.removeItem(CHAT_STORAGE_KEY);
    sessionStorage.removeItem(CHAT_SUMMARY_KEY);
    localStorage.removeItem(CHAT_STORAGE_KEY);
    localStorage.removeItem(CHAT_SUMMARY_KEY);
    miniAiHistory = [];
    miniAiStageQueue = [];
    stopCookingTimer(true);
  }, { once: true });
  initFridge3D();
  document.getElementById('toggleUpper3D')?.addEventListener('click', () => toggleFridgeDoor('upper'));
  document.getElementById('toggleLower3D')?.addEventListener('click', () => toggleFridgeDoor('lower'));
  document.getElementById("upperDoorLeaf")?.addEventListener("click", () => {
    window.ensureAuth(() => { if (!isUpperDoorOpen) setUpperDoor(true); });
  });
  document.getElementById("lowerDoorLeaf")?.addEventListener("click", () => {
    window.ensureAuth(() => { if (!isLowerDoorOpen) setLowerDoor(true); });
  });
  document.getElementById("closeUpperDoorBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (fridge3D) toggleFridgeDoor('upper'); else setUpperDoor(false);
  });
  document.getElementById("closeLowerDoorBtn")?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (fridge3D) toggleFridgeDoor('lower'); else setLowerDoor(false);
  });

  const layerSelect = document.getElementById("foodLayerSelect");
  if (layerSelect) {
    layerSelect.addEventListener("change", (e) => {
      const shelfInput = document.getElementById("shelfLifeInput");
      if (!shelfInput) return;
      shelfInput.value = (e.target.value === "freezer") ? currentAiShelfFreezer : currentAiShelfRefrig;
    });
  }

  document.getElementById("chatUserInput")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendUserChatMessage();
    }
  });

  await checkAuthAndBootstrap();
});
