-- Lease time is separate from request creation time so an old retry cannot be reset mid-flight.
-- 额度租约时间与请求创建时间分离，防止旧请求重试在处理中被重置。
ALTER TABLE send_requests ADD COLUMN reservation_started_at INTEGER;
