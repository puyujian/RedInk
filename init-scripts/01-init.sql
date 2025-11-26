-- 初始化 RedInk 数据库配置和种子数据
CREATE DATABASE IF NOT EXISTS redink CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE redink;

-- 设置全局时区
SET GLOBAL time_zone = '+00:00';

-- 示例：初始化项目设置表（如果不存在）
CREATE TABLE IF NOT EXISTS app_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(128) UNIQUE NOT NULL,
    setting_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO app_settings (setting_key, setting_value)
VALUES ('app_name', 'RedInk AI 生成器')
ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value);
