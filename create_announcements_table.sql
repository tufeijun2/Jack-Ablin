-- 创建弹窗公告表
CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 1,
    trader_uuid VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_announcements_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_announcements_updated_at
    BEFORE UPDATE ON announcements
    FOR EACH ROW
    EXECUTE FUNCTION update_announcements_updated_at();

-- 插入示例数据
INSERT INTO announcements (title, content, active, priority, trader_uuid) VALUES 
('Welcome to Join Exclusive Trading Community', 'Get real-time trading signal alerts, professional strategy analysis, one-on-one trading guidance, and exclusive market analysis reports. Join our exclusive community now and start your path to investment success!', true, 1, '1a2b3c4d-5e6f-7g8h-9i0j-1k2l3m4n5o6p');
