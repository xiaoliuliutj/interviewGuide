package com.interviewguide.knowledgebase.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.interviewguide.knowledgebase.entity.KnowledgeBaseEntity;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import java.util.List;

@Mapper
public interface KnowledgeBaseMapper extends BaseMapper<KnowledgeBaseEntity> {
    @Select("SELECT * FROM knowledge_base WHERE owner_user_id = #{userId} ORDER BY created_at DESC")
    List<KnowledgeBaseEntity> selectByOwner(String userId);
}
