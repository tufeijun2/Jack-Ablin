-- 更新公告表中的trader_uuid为正确的值
UPDATE announcements 
SET trader_uuid = 'b276f479-0910-418f-adc7-8762be79435f' 
WHERE trader_uuid = '1a2b3c4d-5e6f-7g8h-9i0j-1k2l3m4n5o6p';

-- 验证更新结果
SELECT * FROM announcements;
