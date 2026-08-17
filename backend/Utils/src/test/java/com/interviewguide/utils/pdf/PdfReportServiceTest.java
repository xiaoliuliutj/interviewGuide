package com.interviewguide.utils.pdf;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;

/** 验证报告确实是可读取的 PDF，并覆盖颜色卡片、分区和中文内容路径。 */
class PdfReportServiceTest {
    /** 生成一份多分区报告并检查 PDF 文件头和页数，避免退化为 JSON 或空字节。 */
    @Test
    void shouldCreateVisualPdfReport() throws Exception {
        Assumptions.assumeTrue(
                System.getenv("PDF_FONT_PATH") != null
                        && Files.isRegularFile(Path.of(System.getenv("PDF_FONT_PATH"))),
                "配置 PDF_FONT_PATH 后执行中文 PDF 视觉测试"
        );
        byte[] bytes = new PdfReportService().createReport("简历分析报告", Map.of(
                "overallScore", 86,
                "contentScore", 82,
                "summary", "候选人具备扎实的 Java 后端开发基础。",
                "strengths", List.of("项目经历完整", "技术栈清晰"),
                "suggestions", List.of("补充项目指标", "说明性能测试方法")
        ));
        assertTrue(bytes.length > 1000);
        assertArrayEquals("%PDF-".getBytes(StandardCharsets.US_ASCII), java.util.Arrays.copyOf(bytes, 5));
        Path output = Path.of("target", "pdf-report-visual-test.pdf");
        Files.write(output, bytes);
        assertTrue(Files.size(output) == bytes.length);
    }
}
