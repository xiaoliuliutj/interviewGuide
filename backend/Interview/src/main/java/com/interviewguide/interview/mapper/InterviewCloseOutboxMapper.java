package com.interviewguide.interview.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewguide.interview.entity.InterviewCloseOutboxEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface InterviewCloseOutboxMapper extends BaseMapper<InterviewCloseOutboxEntity> {
    @Update("UPDATE interview_close_outbox SET status='PROCESSING', claimed_at=CURRENT_TIMESTAMP WHERE event_id=#{eventId} AND (status IN ('PENDING','FAILED') OR (status='PROCESSING' AND claimed_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes'))")
    int claim(String eventId);

    @Select("SELECT * FROM interview_close_outbox WHERE session_id=#{sessionId} AND status IN ('PENDING','PROCESSING','FAILED') ORDER BY event_id DESC LIMIT 1")
    InterviewCloseOutboxEntity findActiveBySessionId(String sessionId);
}
