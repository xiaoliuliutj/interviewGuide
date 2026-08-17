package com.interviewguide.resume.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewguide.resume.entity.ResumeDeleteOutboxEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface ResumeDeleteOutboxMapper extends BaseMapper<ResumeDeleteOutboxEntity> {
    @Update("UPDATE resume_delete_outbox SET status='PROCESSING', claimed_at=CURRENT_TIMESTAMP WHERE event_id=#{eventId} AND (status IN ('PENDING','FAILED') OR (status='PROCESSING' AND claimed_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes'))")
    int claim(String eventId);

    @Select("SELECT * FROM resume_delete_outbox WHERE resume_id=#{resumeId} AND status IN ('PENDING','PROCESSING','FAILED') ORDER BY event_id DESC LIMIT 1")
    ResumeDeleteOutboxEntity findActiveByResumeId(String resumeId);
}
