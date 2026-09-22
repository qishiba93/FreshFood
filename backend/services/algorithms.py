"""
backend/services/algorithms.py
经典算法实现：
1. 动态规划 Levenshtein 编辑距离算法（用于食材模糊匹配与精准对齐）
2. 指数衰减临期加权评分算法（用于临期食材优先消耗权重推荐）
"""
import math
from datetime import datetime

def levenshtein_distance(s1: str, s2: str) -> int:
    """动态规划实现 Levenshtein 编辑距离"""
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = min(
                    dp[i - 1][j] + 1,      # 插入
                    dp[i][j - 1] + 1,      # 删除
                    dp[i - 1][j - 1] + 1  # 替换
                )
    return dp[m][n]

def fuzzy_ingredient_similarity(name1: str, name2: str) -> float:
    """计算两食材名称的相似度得分 [0.0, 1.0]"""
    n1, n2 = name1.strip().lower(), name2.strip().lower()
    if not n1 or not n2:
        return 0.0
    if n1 == n2 or n1 in n2 or n2 in n1:
        return 1.0

    dist = levenshtein_distance(n1, n2)
    max_len = max(len(n1), len(n2))
    return max(0.0, 1.0 - (dist / max_len))

def calculate_urgency_score(expire_at: datetime) -> float:
    """基于半衰期指数衰减的临期紧迫度算法（48小时内急剧升高）"""
    diff_hours = (expire_at - datetime.now()).total_seconds() / 3600.0
    if diff_hours <= 0:
        return 0.0
    score = 100.0 * math.exp(-diff_hours / 48.0)
    return round(score, 2)