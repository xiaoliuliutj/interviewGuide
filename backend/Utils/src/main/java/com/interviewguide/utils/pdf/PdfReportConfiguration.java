package com.interviewguide.utils.pdf;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

/** 注册供简历和面试模块共同注入的 PDF 报告服务。 */
@AutoConfiguration
public class PdfReportConfiguration {
    /** 创建无状态 PDF 服务，避免每个业务模块各自维护一份排版逻辑。 */
    @Bean
    public PdfReportService pdfReportService() {
        return new PdfReportService();
    }
}
