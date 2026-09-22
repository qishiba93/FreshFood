/**
 * frontend/js/api.js
 * 后端所有 API 网络请求统一封装
 * 包含: 身份鉴权、食材在库、AI智能菜谱、中西餐与技法配置、备菜清单、
 *       星标双向收藏、减碳账本与周榜、美食生活社区、风控审核与图库管理、
 *       全新 AI 厨房管家对话与自动备菜接口
 */

function getHeaders() {
  const token = localStorage.getItem('freshplate_token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['X-FreshFood-Token'] = token;
  }
  return headers;
}

async function checkAuthStatus(res) {
  if (res.status === 401) {
    localStorage.removeItem('freshplate_token');
    localStorage.removeItem('freshplate_role');
    if (window.showForceAuthModal) {
      window.showForceAuthModal();
    } else {
      window.location.href = "/";
    }
    throw new Error("登录已失效，请重新登录");
  }
  return res;
}

export const Api = {
  // ==================== 1. 用户认证与基础信息 ====================
  async login(username, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    return await res.json();
  },

  async register(username, password) {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    return await res.json();
  },

  async getMe() {
    const res = await fetch('/api/auth/me', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  // ==================== 2. 管理员专属运维接口 ====================
  async adminGetUsers() {
    const res = await fetch('/api/auth/admin/users', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async adminCreateUser(userData) {
    const res = await fetch('/api/auth/admin/users', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(userData)
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async adminResetPassword(userId, newPassword) {
    const res = await fetch(`/api/auth/admin/users/${userId}/password`, {
      method: 'PUT',
      headers: getHeaders(),
      body: JSON.stringify({ new_password: newPassword })
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async adminDeleteUser(userId) {
    const res = await fetch(`/api/auth/admin/users/${userId}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async adminGetUserHeatmap(userId) {
    const res = await fetch(`/api/auth/admin/users/${userId}/heatmap`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async adminGetReports(status = "all") {
    const res = await fetch(`/api/admin/audit/reports?status_filter=${status}`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async adminHandleReport(reportId, handleData) {
    const res = await fetch(`/api/admin/audit/reports/${reportId}/handle`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(handleData)
    });
    await checkAuthStatus(res);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "处置操作失败");
    }
    return data;
  },

  async adminGetAuditLogs(params = {}) {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`/api/admin/audit/logs?${query}`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async uploadAdminStandardFile(formData) {
    const token = localStorage.getItem('freshplate_token');
    const headers = {};
    if (token) headers['X-FreshFood-Token'] = token;
    const res = await fetch('/api/admin/food-images/upload-file', {
      method: 'POST',
      headers: headers,
      body: formData
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async createAdminStandardImage(data) {
    const res = await fetch('/api/admin/food-images', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getAdminStandardImages(params = {}) {
    const query = new URLSearchParams(params).toString();
    const res = await fetch(`/api/admin/food-images${query ? `?${query}` : ''}`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async deleteAdminStandardImage(id) {
    const res = await fetch(`/api/admin/food-images/${id}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  // ==================== 3. 冰箱食材管理接口 ====================
  async getPantryItems() {
    const res = await fetch('/api/pantry/items', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async recognizeFood(formData) {
    const token = localStorage.getItem('freshplate_token');
    const headers = {};
    if (token) headers['X-FreshFood-Token'] = token;
    const res = await fetch('/api/pantry/recognize-food', {
      method: 'POST',
      headers: headers,
      body: formData
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async addPantryItem(data) {
    const res = await fetch('/api/pantry/items', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
    await checkAuthStatus(res);
    return res;
  },

  async deductStock(itemId, deductWeight, recipeName = "日常料理") {
    const res = await fetch(`/api/pantry/items/${itemId}/deduct`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ deduct_weight: deductWeight, recipe_name: recipeName })
    });
    await checkAuthStatus(res);
    return res;
  },

  async batchDeductStock(recipeName, items) {
    const res = await fetch('/api/pantry/items/batch-deduct', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ recipe_name: recipeName, items })
    });
    await checkAuthStatus(res);
    return res;
  },

  async discardItem(itemId) {
    const res = await fetch(`/api/pantry/items/${itemId}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return res;
  },

  // ==================== 4. 智能菜谱规划与中西配置接口 ====================
  async getRecipeOptions() {
    const res = await fetch('/api/recipes/config/options', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getAIRecipe(itemId, peopleCount = 2, params = {}) {
    const query = new URLSearchParams({ people_count: peopleCount, ...params }).toString();
    const res = await fetch(`/api/recipes/pantry-item/${itemId}?${query}`, {
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return res;
  },

  async getSpecialRecipe(recipeType, peopleCount = 2, params = {}) {
    const query = new URLSearchParams({ recipe_type: recipeType, people_count: peopleCount, ...params });
    const res = await fetch(`/api/recipes/special?${query.toString()}`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getCustomHealthRecipe(customData) {
    const res = await fetch('/api/recipes/custom-health', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(customData)
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getTodayWhatToEat(peopleCount = 2, params = {}) {
    const query = new URLSearchParams({ people_count: peopleCount, ...params }).toString();
    const res = await fetch(`/api/recipes/today-what-to-eat?${query}`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getChineseCuisines() {
    const res = await fetch('/api/recipes/cuisines/china-regions', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  // ==================== 5. 备菜清单接口 ====================
  async getShoppingItems() {
    const res = await fetch('/api/shopping/items', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async addShoppingBatch(items) {
    const res = await fetch('/api/shopping/batch', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ items })
    });
    await checkAuthStatus(res);
    return res;
  },

  async deleteShoppingItem(id) {
    const res = await fetch(`/api/shopping/items/${id}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return res;
  },

  // ==================== 6. 菜谱收藏夹接口 ====================
  async saveFavorite(recipeData) {
    const res = await fetch('/api/recipes/favorites', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(recipeData)
    });
    await checkAuthStatus(res);

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "收藏菜谱失败");
    }

    data.ok = true;
    data.json = async () => data;
    return data;
  },

  async getFavorites() {
    const res = await fetch('/api/recipes/favorites', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async deleteFavorite(id) {
    const res = await fetch(`/api/recipes/favorites/${id}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "移除收藏失败");
    }
    data.ok = true;
    data.json = async () => data;
    return data;
  },

  async deleteFavoriteByName(recipeName) {
    const res = await fetch(`/api/recipes/favorites/by-name/${encodeURIComponent(recipeName)}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "取消收藏失败");
    }
    data.ok = true;
    data.json = async () => data;
    return data;
  },

  // ==================== 7. 家庭健康画像接口 ====================
  async checkOnboarding() {
    const res = await fetch('/api/health/check-onboarding', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getHealthProfiles() {
    const res = await fetch('/api/health/profiles', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async createHealthProfile(data) {
    const res = await fetch('/api/health/profiles', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
    await checkAuthStatus(res);
    const resData = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(resData.detail || "保存健康画像失败");
    }
    return resData;
  },

  async deleteHealthProfile(id) {
    const res = await fetch(`/api/health/profiles/${id}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  // ==================== 8. 减碳周榜与个人成就 ====================
  async getCarbonLeaderboard() {
    const res = await fetch('/api/carbon/leaderboard/top20', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getMyCarbonSummary() {
    const res = await fetch('/api/carbon/my-summary', { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  // ==================== 9. 美食社区与风控接口 ====================
  async uploadCommunityImage(formData) {
    const token = localStorage.getItem('freshplate_token');
    const headers = {};
    if (token) headers['X-FreshFood-Token'] = token;
    const res = await fetch('/api/community/upload-image', {
      method: 'POST',
      headers: headers,
      body: formData
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async createCommunityPost(data) {
    const res = await fetch('/api/community/posts', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
    await checkAuthStatus(res);
    const resData = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(resData.detail || "发布动态失败");
    }
    return resData;
  },

  async getCommunityPosts(page = 1, pageSize = 20) {
    const res = await fetch(`/api/community/posts?page=${page}&page_size=${pageSize}`, {
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getCommunityPostDetail(postId) {
    const res = await fetch(`/api/community/posts/${postId}`, { headers: getHeaders() });
    await checkAuthStatus(res);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "获取动态详情失败");
    }
    return data;
  },

  async togglePostLike(postId) {
    const res = await fetch(`/api/community/posts/${postId}/like`, {
      method: 'POST',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async getPostComments(postId) {
    const res = await fetch(`/api/community/posts/${postId}/comments`, { headers: getHeaders() });
    await checkAuthStatus(res);
    return await res.json();
  },

  async addPostComment(postId, content) {
    const res = await fetch(`/api/community/posts/${postId}/comments`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify({ content })
    });
    await checkAuthStatus(res);
    return await res.json();
  },

  async deleteCommunityComment(commentId) {
    const res = await fetch(`/api/community/comments/${commentId}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "删除评论失败");
    }
    return data;
  },

  async reportCommunityPost(postId, reportData) {
    const res = await fetch(`/api/community/posts/${postId}/report`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(reportData)
    });
    await checkAuthStatus(res);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "举报提交失败");
    }
    return data;
  },

  async deleteCommunityPost(postId) {
    const res = await fetch(`/api/community/posts/${postId}`, {
      method: 'DELETE',
      headers: getHeaders()
    });
    await checkAuthStatus(res);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || "删除动态失败");
    }
    return data;
  },

  // ==================== 10. AI 厨房管家对话与大厨精讲 ====================
  async chatKitchenAssistant(data) {
    const res = await fetch('/api/chat/kitchen-assistant', {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(data)
    });
    await checkAuthStatus(res);
    const resData = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(resData.detail || "AI 主厨管家响应失败");
    }
    return resData;
  }
};
