-- 添加新字段到announcements表
ALTER TABLE announcements 
ADD COLUMN IF NOT EXISTS popup_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS delay_seconds INTEGER DEFAULT 10,
ADD COLUMN IF NOT EXISTS show_to_members BOOLEAN DEFAULT TRUE;

-- 更新现有记录的默认值
UPDATE announcements 
SET popup_enabled = TRUE, delay_seconds = 10, show_to_members = TRUE 
WHERE popup_enabled IS NULL OR delay_seconds IS NULL OR show_to_members IS NULL;

-- 验证表结构
SELECT column_name, data_type, is_nullable, column_default 
FROM information_schema.columns 
WHERE table_name = 'announcements' 
ORDER BY ordinal_position;
