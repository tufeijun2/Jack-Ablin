-- 修复数据库表结构，添加缺失的trader_uuid列

-- 1. 为documents表添加trader_uuid列
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS trader_uuid UUID;

-- 2. 为videos表添加trader_uuid列
ALTER TABLE videos 
ADD COLUMN IF NOT EXISTS trader_uuid UUID;

-- 3. 更新现有记录的trader_uuid（使用默认的Web_Trader_UUID）
UPDATE documents 
SET trader_uuid = '2e431a66-3423-433b-80a9-c3a4c72b7ffa'::UUID 
WHERE trader_uuid IS NULL;

UPDATE videos 
SET trader_uuid = '2e431a66-3423-433b-80a9-c3a4c72b7ffa'::UUID 
WHERE trader_uuid IS NULL;

-- 4. 为trader_uuid列添加索引以提高查询性能
CREATE INDEX IF NOT EXISTS idx_documents_trader_uuid ON documents(trader_uuid);
CREATE INDEX IF NOT EXISTS idx_videos_trader_uuid ON videos(trader_uuid);

-- 5. 验证表结构
SELECT 
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name IN ('documents', 'videos') 
AND column_name = 'trader_uuid'
ORDER BY table_name;
