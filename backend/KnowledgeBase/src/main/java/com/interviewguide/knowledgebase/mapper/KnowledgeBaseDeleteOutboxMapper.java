package com.interviewguide.knowledgebase.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewguide.knowledgebase.entity.KnowledgeBaseDeleteOutboxEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Update;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface KnowledgeBaseDeleteOutboxMapper extends BaseMapper<KnowledgeBaseDeleteOutboxEntity> {
    @Update("UPDATE knowledge_base_delete_outbox SET status='PROCESSING', claimed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE event_id=#{eventId} AND (status IN ('PENDING','FAILED') OR (status='PROCESSING' AND claimed_at < CURRENT_TIMESTAMP - INTERVAL '5 minutes'))")
    int claim(String eventId);

    @Select("SELECT * FROM knowledge_base_delete_outbox WHERE knowledge_base_id=#{knowledgeBaseId} AND status IN ('PENDING','PROCESSING','FAILED') ORDER BY created_at DESC LIMIT 1")
    KnowledgeBaseDeleteOutboxEntity findActiveByKnowledgeBaseId(Long knowledgeBaseId);
}
