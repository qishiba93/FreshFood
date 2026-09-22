-- =============================================================
-- 智鲜厨房 OS (FreshPlate OS) - 数据库完整初始化脚本
-- 引擎规范: MySQL 8.0+ / InnoDB / utf8mb4
-- 架构设计: 物理外键级联清理 (CASCADE)、长文本医嘱安全存储、
--           本地标准生鲜图库、减碳动态周榜、社区风控工单
-- =============================================================

CREATE DATABASE IF NOT EXISTS `freshplate_db`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `freshplate_db`;

-- 关闭外键检查以安全重建全量表结构
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS `community_reports`;
DROP TABLE IF EXISTS `community_post_comments`;
DROP TABLE IF EXISTS `community_post_likes`;
DROP TABLE IF EXISTS `community_posts`;
DROP TABLE IF EXISTS `user_carbon_logs`;
DROP TABLE IF EXISTS `standard_food_images`;
DROP TABLE IF EXISTS `user_health_profiles`;
DROP TABLE IF EXISTS `user_activities`;
DROP TABLE IF EXISTS `shopping_list`;
DROP TABLE IF EXISTS `favorite_recipes`;
DROP TABLE IF EXISTS `pantry_items`;
DROP TABLE IF EXISTS `users`;

SET FOREIGN_KEY_CHECKS = 1;

-- -------------------------------------------------------------
-- 1. 用户与权限主表 (users)
-- -------------------------------------------------------------
CREATE TABLE `users` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '用户主键ID',
  `username` VARCHAR(64) NOT NULL UNIQUE COMMENT '登录账号名',
  `hashed_password` VARCHAR(128) NOT NULL COMMENT 'Bcrypt 加密密码',
  `role` VARCHAR(16) NOT NULL DEFAULT 'user' COMMENT '角色: super_admin(超级管理员) / admin(管理员) / user(普通用户)',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '账号状态: 1-正常, 0-封禁',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '注册时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户账户主表';

-- -------------------------------------------------------------
-- 2. 家庭成员健康状况档案表 (user_health_profiles)
-- -------------------------------------------------------------
CREATE TABLE `user_health_profiles` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '健康档案主键ID',
  `user_id` INT NOT NULL COMMENT '归属用户ID',
  `member_name` VARCHAR(64) NOT NULL COMMENT '成员称呼 (如: 本人、爸爸、妈妈)',
  `relation` VARCHAR(32) NOT NULL DEFAULT 'self' COMMENT '家庭关系: self/parent/child/spouse/other',
  `conditions` JSON NOT NULL COMMENT '自主填写的身体状况标签列表(JSON)',
  `dietary_notes` VARCHAR(255) NULL DEFAULT NULL COMMENT '特殊忌口与医嘱备忘',
  `is_primary` TINYINT NOT NULL DEFAULT 0 COMMENT '是否为本人主档案: 1-是, 0-否',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '建档时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  INDEX `idx_health_user` (`user_id`),
  CONSTRAINT `fk_health_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户健康状况画像表';

-- -------------------------------------------------------------
-- 3. 冰箱在库食材表 (pantry_items)
-- -------------------------------------------------------------
CREATE TABLE `pantry_items` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '食材主键ID',
  `user_id` INT NOT NULL COMMENT '归属用户ID',
  `name` VARCHAR(64) NOT NULL COMMENT '食材通用名',
  `location` VARCHAR(32) NOT NULL COMMENT '存放温区: refrigeration(保鲜冷藏) / freezer(深冷速冻)',
  `initial_weight` FLOAT NOT NULL DEFAULT 0.0 COMMENT '初始录入克重',
  `remaining_weight` FLOAT NOT NULL DEFAULT 0.0 COMMENT '当前剩余克重',
  `unit` VARCHAR(16) NOT NULL DEFAULT '克' COMMENT '计量单位',
  `expire_at` DATETIME NOT NULL COMMENT '保质期截止时间',
  `image_url` VARCHAR(255) NULL DEFAULT NULL COMMENT '本地食材图路径',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '录入时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  INDEX `idx_pantry_user` (`user_id`),
  INDEX `idx_pantry_expire` (`expire_at`),
  CONSTRAINT `fk_pantry_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='冰箱在库食材表';

-- -------------------------------------------------------------
-- 4. 收藏菜谱表 (favorite_recipes - calories与glycemic_info已升级为TEXT)
-- -------------------------------------------------------------
CREATE TABLE `favorite_recipes` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '菜谱主键ID',
  `user_id` INT NOT NULL COMMENT '归属用户ID',
  `recipe_name` VARCHAR(128) NOT NULL COMMENT '菜品名称',
  `category` VARCHAR(32) NOT NULL DEFAULT 'custom' COMMENT '分类: custom/custom_health/gout/goiter/low_fat/diabetic/today/community_share',
  `difficulty` VARCHAR(64) NULL DEFAULT NULL COMMENT '烹饪难度与耗时',
  `calories` TEXT NULL DEFAULT NULL COMMENT '热量或基础指标(TEXT长文本，确保长文本无损存入)',
  `glycemic_info` TEXT NULL DEFAULT NULL COMMENT '临床调理医嘱指标(TEXT长文本，确保甲状腺控碘长医嘱安全存入)',
  `ingredients_needed` JSON NOT NULL COMMENT '主配食材配比清单(JSON)',
  `pantry_staples` TEXT NULL DEFAULT NULL COMMENT '常备调味品',
  `cooking_steps` JSON NOT NULL COMMENT '烹饪步骤清单(JSON)',
  `chef_tips` TEXT NULL DEFAULT NULL COMMENT '大厨烹饪窍门',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '收藏时间',
  INDEX `idx_fav_user` (`user_id`),
  CONSTRAINT `fk_fav_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户收藏菜谱表';

-- -------------------------------------------------------------
-- 5. 备菜采购清单表 (shopping_list)
-- -------------------------------------------------------------
CREATE TABLE `shopping_list` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '备菜项主键ID',
  `user_id` INT NOT NULL COMMENT '归属用户ID',
  `name` VARCHAR(64) NOT NULL COMMENT '需采买食材名称',
  `amount` VARCHAR(64) NULL DEFAULT '适量' COMMENT '建议购买量',
  `source_recipe` VARCHAR(128) NULL DEFAULT '自主添加' COMMENT '来源菜谱',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '加入清单时间',
  INDEX `idx_shopping_user` (`user_id`),
  CONSTRAINT `fk_shopping_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='备菜清单采购表';

-- -------------------------------------------------------------
-- 6. 官方统一标准食材图库表 (standard_food_images - 支持单食材多图)
-- -------------------------------------------------------------
CREATE TABLE `standard_food_images` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '图库主键ID',
  `food_name` VARCHAR(64) NOT NULL COMMENT '标准食材名',
  `synonyms` VARCHAR(255) NULL DEFAULT NULL COMMENT '别名同义词 (逗号分隔)',
  `category` VARCHAR(32) NOT NULL DEFAULT 'other' COMMENT '分类: vegetable/meat/seafood/fruit/staple/other',
  `image_url` VARCHAR(255) NOT NULL COMMENT '本地高清图片路径',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '收录时间',
  INDEX `idx_std_food_name` (`food_name`),
  INDEX `idx_std_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='官方标准食材图库表';

-- -------------------------------------------------------------
-- 7. 用户减碳明细账本表 (user_carbon_logs)
-- -------------------------------------------------------------
CREATE TABLE `user_carbon_logs` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '减碳日志主键ID',
  `user_id` INT NOT NULL COMMENT '归属用户ID',
  `item_name` VARCHAR(64) NOT NULL COMMENT '消耗食材名',
  `weight_grams` FLOAT NOT NULL COMMENT '消耗克重',
  `carbon_saved_grams` FLOAT NOT NULL COMMENT '减碳贡献克数 (克 CO2e)',
  `source_recipe` VARCHAR(128) NULL DEFAULT '日常烹饪' COMMENT '制作菜谱名',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '做菜核算时间',
  INDEX `idx_carbon_user` (`user_id`),
  INDEX `idx_carbon_created` (`created_at`),
  CONSTRAINT `fk_carbon_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户减碳账本明细表';

-- -------------------------------------------------------------
-- 8. 美食社区做菜动态表 (community_posts - 包含 recipe_data 菜谱绑定)
-- -------------------------------------------------------------
CREATE TABLE `community_posts` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '动态主键ID',
  `user_id` INT NOT NULL COMMENT '作者用户ID',
  `title` VARCHAR(128) NOT NULL COMMENT '菜品名称或心得标题',
  `content` TEXT NOT NULL COMMENT '做菜心得与操作体会',
  `image_url` VARCHAR(255) NOT NULL COMMENT '成品图片路径',
  `recipe_data` JSON NULL DEFAULT NULL COMMENT '绑定的完整菜谱数据(JSON，供食友一键收藏)',
  `likes_count` INT NOT NULL DEFAULT 0 COMMENT '获赞总数',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1-正常展示, 0-违规下架屏蔽',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发布时间',
  INDEX `idx_post_user` (`user_id`),
  INDEX `idx_post_status_created` (`status`, `created_at`),
  CONSTRAINT `fk_post_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='美食生活社区打卡发帖表';

-- -------------------------------------------------------------
-- 9. 社区动态点赞防重表 (community_post_likes)
-- -------------------------------------------------------------
CREATE TABLE `community_post_likes` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '点赞主键ID',
  `post_id` INT NOT NULL COMMENT '帖子ID',
  `user_id` INT NOT NULL COMMENT '点赞用户ID',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '点赞时间',
  UNIQUE KEY `uq_post_user_like` (`post_id`, `user_id`),
  INDEX `idx_like_post` (`post_id`),
  CONSTRAINT `fk_like_post`
    FOREIGN KEY (`post_id`) REFERENCES `community_posts` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_like_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='社区点赞记录表';

-- -------------------------------------------------------------
-- 10. 社区动态食友评论表 (community_post_comments)
-- -------------------------------------------------------------
CREATE TABLE `community_post_comments` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '评论主键ID',
  `post_id` INT NOT NULL COMMENT '帖子ID',
  `user_id` INT NOT NULL COMMENT '评论人用户ID',
  `content` VARCHAR(500) NOT NULL COMMENT '评论内容',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 1-正常, 0-屏蔽',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '评论时间',
  INDEX `idx_comment_post` (`post_id`, `status`),
  CONSTRAINT `fk_comment_post`
    FOREIGN KEY (`post_id`) REFERENCES `community_posts` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_comment_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='社区食友评论留言表';

-- -------------------------------------------------------------
-- 11. 社区违规内容举报风控表 (community_reports)
-- -------------------------------------------------------------
CREATE TABLE `community_reports` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '举报工单主键ID',
  `post_id` INT NOT NULL COMMENT '被举报帖子ID',
  `reporter_id` INT NOT NULL COMMENT '提交举报用户ID',
  `reason` VARCHAR(64) NOT NULL COMMENT '违规类型: violence/porn/spam/unrelated/other',
  `detail` VARCHAR(255) NULL DEFAULT NULL COMMENT '举报说明',
  `status` VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '处理状态: pending/approved/rejected',
  `admin_note` VARCHAR(255) NULL DEFAULT NULL COMMENT '管理员批注',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '举报时间',
  `handled_at` DATETIME NULL DEFAULT NULL COMMENT '结单时间',
  INDEX `idx_report_post` (`post_id`),
  INDEX `idx_report_status` (`status`),
  CONSTRAINT `fk_report_post`
    FOREIGN KEY (`post_id`) REFERENCES `community_posts` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_report_user`
    FOREIGN KEY (`reporter_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='社区风控举报工单处置表';

-- -------------------------------------------------------------
-- 12. 全员行为操作审计日志表 (user_activities)
-- -------------------------------------------------------------
CREATE TABLE `user_activities` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '审计日志主键ID',
  `user_id` INT NOT NULL COMMENT '归属用户ID',
  `activity_type` VARCHAR(32) NOT NULL COMMENT '类型: add/consume/collect/post/like/comment/report/login',
  `note` VARCHAR(255) NULL DEFAULT NULL COMMENT '操作描述',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录时间',
  INDEX `idx_act_user_date` (`user_id`, `created_at`),
  INDEX `idx_act_type` (`activity_type`),
  CONSTRAINT `fk_activity_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
    ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='全员行为操作审计流水表';


-- =============================================================
-- 预置测试数据 (初始密码统一为: 123456)
-- =============================================================

-- 1. 账号结构：1 个超级管理员 + 3 个普通用户 (user1, user2, user3)
INSERT INTO `users` (`id`, `username`, `hashed_password`, `role`, `status`) VALUES
(1, 'admin', '$2b$12$e80yq9gV0gXjX7mQ3uU7bO6V7kH9F4lF4m7I5B1M7H4p2Y5Z0K2Za', 'super_admin', 1),
(2, 'user1', '$2b$12$e80yq9gV0gXjX7mQ3uU7bO6V7kH9F4lF4m7I5B1M7H4p2Y5Z0K2Za', 'user', 1),
(3, 'user2', '$2b$12$e80yq9gV0gXjX7mQ3uU7bO6V7kH9F4lF4m7I5B1M7H4p2Y5Z0K2Za', 'user', 1),
(4, 'user3', '$2b$12$e80yq9gV0gXjX7mQ3uU7bO6V7kH9F4lF4m7I5B1M7H4p2Y5Z0K2Za', 'user', 1);

-- 2. 预置自主手写健康状况画像 (user1 包含多位家属)
INSERT INTO `user_health_profiles` (`user_id`, `member_name`, `relation`, `conditions`, `dietary_notes`, `is_primary`) VALUES
(2, '本人', 'self', '["痛风尿酸偏高", "二型糖尿病需控糖"]', '严格少肉汤与低果糖饮品', 1),
(2, '爸爸', 'parent', '["高血压", "少油少盐"]', '清淡饮食，避免高钠调味品', 0),
(2, '妈妈', 'parent', '["甲状腺调理"]', '避免过量高碘海带紫菜，十字花科煮透食用', 0),
(3, '本人', 'self', '["健身减脂", "高蛋白"]', '偏好白灼和少油煎烤', 1),
(4, '本人', 'self', '["慢性胃炎", "不能吃生冷辛辣"]', '以温热炖煮为主', 1);

-- 3. 预置官方标准食材图库 (每种食材包含 3 张本地标准图片)
INSERT INTO `standard_food_images` (`food_name`, `synonyms`, `category`, `image_url`) VALUES
-- 番茄 (3张)
('番茄', '西红柿,小番茄,洋柿子', 'vegetable', '/static/standards/tomato_1.jpg'),
('番茄', '西红柿,小番茄,洋柿子', 'vegetable', '/static/standards/tomato_2.jpg'),
('番茄', '西红柿,小番茄,洋柿子', 'vegetable', '/static/standards/tomato_3.jpg'),
-- 西兰花 (3张)
('西兰花', '绿菜花,青花菜', 'vegetable', '/static/standards/broccoli_1.jpg'),
('西兰花', '绿菜花,青花菜', 'vegetable', '/static/standards/broccoli_2.jpg'),
('西兰花', '绿菜花,青花菜', 'vegetable', '/static/standards/broccoli_3.jpg'),
-- 鸡胸肉 (3张)
('鸡胸肉', '冷鲜鸡胸,鸡肉,鸡柳', 'meat', '/static/standards/chicken_breast_1.jpg'),
('鸡胸肉', '冷鲜鸡胸,鸡肉,鸡柳', 'meat', '/static/standards/chicken_breast_2.jpg'),
('鸡胸肉', '冷鲜鸡胸,鸡肉,鸡柳', 'meat', '/static/standards/chicken_breast_3.jpg'),
-- 原切牛肉 (3张)
('原切牛肉', '牛排,牛里脊,牛腩,肥牛', 'meat', '/static/standards/beef_1.jpg'),
('原切牛肉', '牛排,牛里脊,牛腩,肥牛', 'meat', '/static/standards/beef_2.jpg'),
('原切牛肉', '牛排,牛里脊,牛腩,肥牛', 'meat', '/static/standards/beef_3.jpg'),
-- 鲜鸡蛋 (3张)
('鲜鸡蛋', '鸡蛋,洋鸡蛋,土鸡蛋,无菌蛋', 'meat', '/static/standards/egg_1.jpg'),
('鲜鸡蛋', '鸡蛋,洋鸡蛋,土鸡蛋,无菌蛋', 'meat', '/static/standards/egg_2.jpg'),
('鲜鸡蛋', '鸡蛋,洋鸡蛋,土鸡蛋,无菌蛋', 'meat', '/static/standards/egg_3.jpg'),
-- 黑虎虾仁 (3张)
('黑虎虾仁', '青虾仁,基围虾,大虾,鲜虾', 'seafood', '/static/standards/shrimp_1.jpg'),
('黑虎虾仁', '青虾仁,基围虾,大虾,鲜虾', 'seafood', '/static/standards/shrimp_2.jpg'),
('黑虎虾仁', '青虾仁,基围虾,大虾,鲜虾', 'seafood', '/static/standards/shrimp_3.jpg'),
-- 黄瓜 (3张)
('黄瓜', '青瓜,水果黄瓜', 'vegetable', '/static/standards/cucumber_1.jpg'),
('黄瓜', '青瓜,水果黄瓜', 'vegetable', '/static/standards/cucumber_2.jpg'),
('黄瓜', '青瓜,水果黄瓜', 'vegetable', '/static/standards/cucumber_3.jpg'),
-- 土豆 (3张)
('土豆', '马铃薯,洋芋', 'vegetable', '/static/standards/potato_1.jpg'),
('土豆', '马铃薯,洋芋', 'vegetable', '/static/standards/potato_2.jpg'),
('土豆', '马铃薯,洋芋', 'vegetable', '/static/standards/potato_3.jpg'),
-- 嫩豆腐 (3张)
('嫩豆腐', '豆腐,老豆腐,水豆腐,豆干', 'vegetable', '/static/standards/tofu_1.jpg'),
('嫩豆腐', '豆腐,老豆腐,水豆腐,豆干', 'vegetable', '/static/standards/tofu_2.jpg'),
('嫩豆腐', '豆腐,老豆腐,水豆腐,豆干', 'vegetable', '/static/standards/tofu_3.jpg'),
-- 胡萝卜 (3张)
('胡萝卜', '红萝卜,红参', 'vegetable', '/static/standards/carrot_1.jpg'),
('胡萝卜', '红萝卜,红参', 'vegetable', '/static/standards/carrot_2.jpg'),
('胡萝卜', '红萝卜,红参', 'vegetable', '/static/standards/carrot_3.jpg'),
-- 五花猪肉 (3张)
('五花猪肉', '猪肉,五花肉,里脊肉,排骨', 'meat', '/static/standards/pork_1.jpg'),
('五花猪肉', '猪肉,五花肉,里脊肉,排骨', 'meat', '/static/standards/pork_2.jpg'),
('五花猪肉', '猪肉,五花肉,里脊肉,排骨', 'meat', '/static/standards/pork_3.jpg'),
-- 红富士苹果 (3张)
('红富士苹果', '苹果,青苹果,红富士', 'fruit', '/static/standards/apple_1.jpg'),
('红富士苹果', '苹果,青苹果,红富士', 'fruit', '/static/standards/apple_2.jpg'),
('红富士苹果', '苹果,青苹果,红富士', 'fruit', '/static/standards/apple_3.jpg'),
-- 香蕉 (3张)
('香蕉', '香蕉,芭蕉', 'fruit', '/static/standards/banana_1.jpg'),
('香蕉', '香蕉,芭蕉', 'fruit', '/static/standards/banana_2.jpg'),
('香蕉', '香蕉,芭蕉', 'fruit', '/static/standards/banana_3.jpg'),
-- 白蘑菇 (3张)
('白蘑菇', '香菇,口蘑,金针菇,平菇', 'vegetable', '/static/standards/mushroom_1.jpg'),
('白蘑菇', '香菇,口蘑,金针菇,平菇', 'vegetable', '/static/standards/mushroom_2.jpg'),
('白蘑菇', '香菇,口蘑,金针菇,平菇', 'vegetable', '/static/standards/mushroom_3.jpg'),
-- 洋葱 (3张)
('洋葱', '圆葱,紫洋葱,白洋葱', 'vegetable', '/static/standards/onion_1.jpg'),
('洋葱', '圆葱,紫洋葱,白洋葱', 'vegetable', '/static/standards/onion_2.jpg'),
('洋葱', '圆葱,紫洋葱,白洋葱', 'vegetable', '/static/standards/onion_3.jpg'),
-- 菠菜 (3张)
('菠菜', '小菠菜,绿叶菜', 'vegetable', '/static/standards/spinach_1.jpg'),
('菠菜', '小菠菜,绿叶菜', 'vegetable', '/static/standards/spinach_2.jpg'),
('菠菜', '小菠菜,绿叶菜', 'vegetable', '/static/standards/spinach_3.jpg');

-- 4. 预置在库食材 (直接对接本地爬取的高清图片)
INSERT INTO `pantry_items` (`user_id`, `name`, `location`, `initial_weight`, `remaining_weight`, `unit`, `expire_at`, `image_url`) VALUES
(2, '鲜嫩鸡胸肉', 'refrigeration', 450.0, 450.0, '克', DATE_ADD(NOW(), INTERVAL 3 DAY), '/static/standards/chicken_breast_1.jpg'),
(2, '新鲜西兰花', 'refrigeration', 300.0, 300.0, '克', DATE_ADD(NOW(), INTERVAL 2 DAY), '/static/standards/broccoli_1.jpg'),
-- 临期急需消耗食材 (剩余 18 小时，触发优先消灭)
(2, '番茄', 'refrigeration', 300.0, 300.0, '克', DATE_ADD(NOW(), INTERVAL 18 HOUR), '/static/standards/tomato_1.jpg'),
(2, '鲜鸡蛋', 'refrigeration', 600.0, 600.0, '克', DATE_ADD(NOW(), INTERVAL 7 DAY), '/static/standards/egg_1.jpg'),
(2, '原切牛肉', 'freezer', 800.0, 600.0, '克', DATE_ADD(NOW(), INTERVAL 45 DAY), '/static/standards/beef_1.jpg'),
(2, '黑虎虾仁', 'freezer', 500.0, 400.0, '克', DATE_ADD(NOW(), INTERVAL 60 DAY), '/static/standards/shrimp_1.jpg'),
-- user2 与 user3 的库存
(3, '鲜嫩鸡胸肉', 'refrigeration', 500.0, 500.0, '克', DATE_ADD(NOW(), INTERVAL 4 DAY), '/static/standards/chicken_breast_2.jpg'),
(4, '土豆', 'refrigeration', 600.0, 600.0, '克', DATE_ADD(NOW(), INTERVAL 10 DAY), '/static/standards/potato_1.jpg');

-- 5. 预置本周减碳明细账本 (呈现三位食友名次梯队)
INSERT INTO `user_carbon_logs` (`user_id`, `item_name`, `weight_grams`, `carbon_saved_grams`, `source_recipe`, `created_at`) VALUES
-- user1 居第 1 名 (共 12210g)
(2, '原切牛肉', 200.0, 12000.0, '黑椒小牛排', NOW()),
(2, '番茄', 150.0, 210.0, '番茄烩蛋', DATE_SUB(NOW(), INTERVAL 1 DAY)),
-- user2 居第 2 名 (共 4975g)
(3, '黑虎虾仁', 300.0, 3600.0, '葱油白灼虾', NOW()),
(3, '鲜嫩鸡胸肉', 250.0, 1375.0, '香草煎鸡胸', DATE_SUB(NOW(), INTERVAL 2 DAY)),
-- user3 居第 3 名 (共 180g)
(4, '土豆', 300.0, 180.0, '清炒土豆丝', NOW());

-- 6. 预置美食社区发帖打卡 (绑定完整菜谱数据，供食友查看与一键收藏)
INSERT INTO `community_posts` (`id`, `user_id`, `title`, `content`, `image_url`, `recipe_data`, `likes_count`, `status`, `created_at`) VALUES
(
  1,
  2,
  '葱油白灼黑虎虾',
  '按照家里的控糖和少嘌呤要求做的，虾肉鲜甜紧实，白灼断生捞出淋葱油，极度下饭！',
  '/static/standards/shrimp_1.jpg',
  '{"recipe_name": "葱油白灼黑虎虾", "difficulty": "初级 · 12分钟", "health_metric": "单份总嘌呤约 35mg (低负荷)", "ingredients_needed": [{"name": "黑虎虾仁", "amount": "200克"}, {"name": "小葱", "amount": "2根"}], "cooking_steps": ["葱白切段炸出清香葱油；", "沸水下黑虎虾仁焯烫50秒卷曲捞起；", "摆盘淋上热葱油与少许生抽。"], "chef_tips": "水要滚沸，虾身变红紧绷立即捞出，肉质最嫩。"}',
  16,
  1,
  DATE_SUB(NOW(), INTERVAL 2 HOUR)
),
(
  2,
  3,
  '金玉番茄滑鸡柳',
  '低脂高蛋白的减脂大餐，酸甜开胃，浓郁的番茄汁裹满鲜嫩鸡肉，单份热量才310大卡！',
  '/static/standards/tomato_1.jpg',
  '{"recipe_name": "金玉番茄滑鸡柳", "difficulty": "初级 · 15分钟", "health_metric": "单份热量约 310 kcal", "ingredients_needed": [{"name": "鸡胸肉", "amount": "250克"}, {"name": "番茄", "amount": "2个"}], "cooking_steps": ["鸡胸切柳少许蛋清抓匀；", "番茄去皮切块炒出红沙红油；", "下鸡柳滑炒变白收汁起锅。"], "chef_tips": "番茄加一撮细盐翻炒出沙速度更快。"}',
  28,
  1,
  DATE_SUB(NOW(), INTERVAL 4 HOUR)
),
(
  3,
  4,
  '推销广告内容',
  '这是一条供管理员在“违规反馈处置台”测试驳回或下架屏蔽功能的模拟测试广告。',
  '/static/standards/potato_1.jpg',
  NULL,
  0,
  1,
  DATE_SUB(NOW(), INTERVAL 1 DAY)
);

-- 预置社区点赞与评论
INSERT INTO `community_post_likes` (`post_id`, `user_id`) VALUES (1, 3), (1, 4), (2, 2);
INSERT INTO `community_post_comments` (`post_id`, `user_id`, `content`) VALUES
(1, 3, '成色非常漂亮，原汁原味看着太有食欲了！'),
(1, 4, '做法好简单，今晚我也照着做一份！'),
(2, 2, '这个番茄汁太赞了，我也收藏了！');

-- 7. 预置同帖多用户举报工单 (测试管理员端的自动合并聚合功能)
INSERT INTO `community_reports` (`post_id`, `reporter_id`, `reason`, `detail`, `status`, `created_at`) VALUES
(3, 2, 'spam', '推销广告导流，与美食烹饪无关，申请下架。', 'pending', DATE_SUB(NOW(), INTERVAL 20 MINUTE)),
(3, 3, 'spam', '全是营销推广链接，影响社区氛围。', 'pending', DATE_SUB(NOW(), INTERVAL 10 MINUTE));

-- 8. 预置收藏菜谱与采购清单 (支持长文本调理医嘱)
INSERT INTO `favorite_recipes` (`user_id`, `recipe_name`, `category`, `difficulty`, `calories`, `glycemic_info`, `ingredients_needed`, `pantry_staples`, `cooking_steps`, `chef_tips`) VALUES
(
  2,
  '葱油白灼黑虎虾',
  'custom',
  '初级 · 12分钟',
  '🔥 约 220 kcal',
  '单份总嘌呤约 35mg (低负荷)',
  '[{"name": "黑虎虾仁", "amount": "200克", "from_pantry": true}, {"name": "小葱", "amount": "2根", "from_pantry": false}]',
  '热葱油10ml、薄盐生抽5ml',
  '["葱白切段炸出清香葱油；", "沸水下黑虎虾仁焯烫50秒卷曲捞起；", "摆盘淋上热葱油与少许生抽。"]',
  '水要滚沸，虾身变红紧绷立即捞出，肉质最嫩。'
),
(
  2,
  '清蒸西兰花炖鸡柳',
  'goiter',
  '初级 · 15分钟',
  NULL,
  '单份碘含量把控在 35mcg 适碘安全范围；临床提示：十字花科蔬菜（西兰花）含有硫苷物质，烹饪前必须在滚沸热水中焯烫熟透 2 分钟以上，以灭活致甲状腺肿物质，确保内分泌代谢安全。',
  '[{"name": "鸡胸肉", "amount": "200克", "from_pantry": true}, {"name": "西兰花", "amount": "150克", "from_pantry": true}]',
  '生姜3片、无碘低钠盐2克、清亮花生油5ml',
  '["西兰花洗净切小朵，沸水中彻底焯透捞出沥干；", "鸡胸肉切薄柳抓匀少许蛋清与生姜片；", "蒸锅上汽大火清蒸8分钟出锅淋少许热油。"]',
  '大厨火候：焯烫务必到位，清蒸锁住鸡肉原汁。'
);

INSERT INTO `shopping_list` (`user_id`, `name`, `amount`, `source_recipe`) VALUES
(2, '优质小葱', '1小把', '葱油白灼黑虎虾'),
(2, '薄盐生抽', '1瓶', '厨房基础常备补给');

-- 9. 预置全员行为审计日志 (支撑热力总图与审计流水)
INSERT INTO `user_activities` (`user_id`, `activity_type`, `note`, `created_at`) VALUES
(2, 'add', '录入食材:原切牛肉', DATE_SUB(NOW(), INTERVAL 3 DAY)),
(2, 'consume', '做菜消耗:原切牛肉(减碳12000g)', NOW()),
(2, 'collect', '收藏菜谱:葱油白灼黑虎虾', DATE_SUB(NOW(), INTERVAL 1 DAY)),
(2, 'collect', '收藏菜谱:清蒸西兰花炖鸡柳', DATE_SUB(NOW(), INTERVAL 1 DAY)),
(2, 'post', '发布社区动态:葱油白灼黑虎虾', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
(2, 'report', '举报动态ID:3(原因:spam)', DATE_SUB(NOW(), INTERVAL 20 MINUTE)),
(3, 'post', '发布社区动态:金玉番茄滑鸡柳', DATE_SUB(NOW(), INTERVAL 4 HOUR)),
(3, 'like', '点赞动态ID:1', DATE_SUB(NOW(), INTERVAL 1 HOUR)),
(3, 'report', '举报动态ID:3(原因:spam)', DATE_SUB(NOW(), INTERVAL 10 MINUTE)),
(3, 'consume', '做菜消耗:黑虎虾仁(减碳3600g)', NOW()),
(4, 'comment', '评论动态ID:1', DATE_SUB(NOW(), INTERVAL 30 MINUTE)),
(4, 'consume', '做菜消耗:土豆(减碳180g)', NOW());