package com.interviewguide.utils.pdf;

import java.awt.Color;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDFont;
import org.apache.pdfbox.pdmodel.font.PDType0Font;

/**
 * 生成简历分析和面试报告共用的视觉化 PDF。
 *
 * <p>服务只把 Java 已持久化的展示数据排版为文件，不访问 Agent、数据库或业务实体。</p>
 */
public class PdfReportService {
    private static final float PAGE_WIDTH = PDRectangle.A4.getWidth();
    private static final float PAGE_HEIGHT = PDRectangle.A4.getHeight();
    private static final float MARGIN = 48F;
    private static final Color PRIMARY = new Color(31, 78, 121);
    private static final Color ACCENT = new Color(42, 157, 143);
    private static final Color LIGHT = new Color(239, 246, 252);
    private static final Color TEXT = new Color(45, 55, 72);

    /**
     * 根据报告标题和结构化数据生成真实 PDF 字节流。
     *
     * <p>页面包含深色标题条、彩色分隔线、评分卡片、分区标题和自动换行正文；内容过长时自动分页。</p>
     */
    public byte[] createReport(String title, Map<String, Object> report) {
        try (PDDocument document = new PDDocument(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            PDFont font = loadChineseFont(document);
            PdfCursor cursor = createPage(document, font, title);
            cursor = drawScoreCards(document, cursor, font, report);
            cursor = drawSection(document, cursor, font, "报告内容", report);
            drawFooter(cursor.stream, font, cursor.pageNumber);
            cursor.stream.close();
            document.save(output);
            return output.toByteArray();
        } catch (IOException error) {
            throw new IllegalStateException("PDF 报告生成失败", error);
        }
    }

    /** 加载部署环境配置的中文字体，拒绝生成不可读的中文 PDF。 */
    private PDFont loadChineseFont(PDDocument document) throws IOException {
        String fontPath = System.getenv("PDF_FONT_PATH");
        if (fontPath == null || fontPath.isBlank() || !new File(fontPath).isFile()) {
            throw new IllegalStateException("未配置可用中文字体，请设置 PDF_FONT_PATH");
        }
        return PDType0Font.load(document, new File(fontPath));
    }

    /** 新建页面并绘制标题色块、生成时间和装饰性分隔线。 */
    private PdfCursor createPage(PDDocument document, PDFont font, String title) throws IOException {
        PDPage page = new PDPage(PDRectangle.A4);
        document.addPage(page);
        PDPageContentStream stream = new PDPageContentStream(document, page);
        stream.setNonStrokingColor(PRIMARY);
        stream.addRect(0, PAGE_HEIGHT - 118F, PAGE_WIDTH, 118F);
        stream.fill();
        stream.setNonStrokingColor(Color.WHITE);
        stream.beginText();
        stream.setFont(font, 23F);
        stream.newLineAtOffset(MARGIN, PAGE_HEIGHT - 62F);
        stream.showText(title);
        stream.endText();
        stream.setFont(font, 10F);
        stream.beginText();
        stream.newLineAtOffset(MARGIN, PAGE_HEIGHT - 88F);
        stream.showText("生成时间：" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")));
        stream.endText();
        stream.setNonStrokingColor(ACCENT);
        stream.addRect(MARGIN, PAGE_HEIGHT - 126F, 90F, 4F);
        stream.fill();
        return new PdfCursor(stream, document.getNumberOfPages(), PAGE_HEIGHT - 158F);
    }

    /** 绘制常见评分字段为彩色卡片；没有评分字段时不占用页面空间。 */
    private PdfCursor drawScoreCards(PDDocument document, PdfCursor cursor, PDFont font, Map<String, Object> report) throws IOException {
        List<String> keys = List.of("overallScore", "contentScore", "structureScore", "skillMatchScore", "expressionScore", "projectScore", "score");
        int cardIndex = 0;
        for (String key : keys) {
            Object value = report.get(key);
            if (!(value instanceof Number)) {
                continue;
            }
            if (cardIndex == 0) {
                cursor = ensureSpace(document, cursor, font, 105F);
                cursor = drawHeading(cursor, font, "评分概览");
            }
            float x = MARGIN + cardIndex * 83F;
            cursor.stream.setNonStrokingColor(LIGHT);
            cursor.stream.addRect(x, cursor.y - 68F, 72F, 58F);
            cursor.stream.fill();
            cursor.stream.setNonStrokingColor(ACCENT);
            cursor.stream.addRect(x, cursor.y - 68F, 72F, 5F);
            cursor.stream.fill();
            writeText(cursor.stream, font, TEXT, 9F, x + 8F, cursor.y - 29F, displayName(key));
            writeText(cursor.stream, font, PRIMARY, 19F, x + 20F, cursor.y - 52F, value + "");
            cardIndex++;
            if (cardIndex == 6) {
                cursor.y -= 82F;
                break;
            }
        }
        return cardIndex == 0 ? cursor : new PdfCursor(cursor.stream, cursor.pageNumber, cursor.y - 12F);
    }

    /** 递归绘制结构化字段，列表使用圆点，嵌套对象使用二级标题。 */
    private PdfCursor drawSection(PDDocument document, PdfCursor cursor, PDFont font, String heading, Map<String, Object> values) throws IOException {
        cursor = ensureSpace(document, cursor, font, 64F);
        cursor = drawHeading(cursor, font, heading);
        for (Map.Entry<String, Object> entry : values.entrySet()) {
            if (entry.getValue() == null || entry.getKey().endsWith("Score")) {
                continue;
            }
            cursor = drawValue(document, cursor, font, displayName(entry.getKey()), entry.getValue());
        }
        return cursor;
    }

    /** 根据字段类型绘制普通文本、列表或嵌套结构。 */
    @SuppressWarnings("unchecked")
    private PdfCursor drawValue(PDDocument document, PdfCursor cursor, PDFont font, String label, Object value) throws IOException {
        if (value instanceof Map<?, ?> raw) {
            Map<String, Object> nested = (Map<String, Object>) raw;
            return drawSection(document, cursor, font, label, nested);
        }
        if (value instanceof List<?> list) {
            cursor = ensureSpace(document, cursor, font, 34F);
            writeText(cursor.stream, font, PRIMARY, 11F, MARGIN, cursor.y, label);
            cursor.y -= 20F;
            for (Object item : list) {
                cursor = drawParagraph(document, cursor, font, "• " + String.valueOf(item), 11F);
            }
            return cursor;
        }
        cursor = ensureSpace(document, cursor, font, 34F);
        writeText(cursor.stream, font, PRIMARY, 11F, MARGIN, cursor.y, label);
        cursor.y -= 20F;
        return drawParagraph(document, cursor, font, String.valueOf(value), 11F);
    }

    /** 按固定宽度换行绘制正文，避免长文本越出页面。 */
    private PdfCursor drawParagraph(PDDocument document, PdfCursor cursor, PDFont font, String content, float size) throws IOException {
        String normalized = content.replace('\n', ' ').trim();
        int start = 0;
        while (start < normalized.length()) {
            int end = Math.min(start + 42, normalized.length());
            cursor = ensureSpace(document, cursor, font, 22F);
            writeText(cursor.stream, font, TEXT, size, MARGIN + 8F, cursor.y, normalized.substring(start, end));
            cursor.y -= 18F;
            start = end;
        }
        return new PdfCursor(cursor.stream, cursor.pageNumber, cursor.y - 8F);
    }

    /** 绘制分区标题及细分隔线。 */
    private PdfCursor drawHeading(PdfCursor cursor, PDFont font, String heading) throws IOException {
        writeText(cursor.stream, font, PRIMARY, 15F, MARGIN, cursor.y, heading);
        cursor.stream.setStrokingColor(new Color(203, 213, 224));
        cursor.stream.setLineWidth(0.8F);
        cursor.stream.moveTo(MARGIN, cursor.y - 9F);
        cursor.stream.lineTo(PAGE_WIDTH - MARGIN, cursor.y - 9F);
        cursor.stream.stroke();
        return new PdfCursor(cursor.stream, cursor.pageNumber, cursor.y - 30F);
    }

    /** 在空间不足时关闭当前页并创建保持同样视觉结构的新页。 */
    private PdfCursor ensureSpace(PDDocument document, PdfCursor cursor, PDFont font, float requiredHeight) throws IOException {
        if (cursor.y - requiredHeight > 55F) {
            return cursor;
        }
        drawFooter(cursor.stream, font, cursor.pageNumber);
        cursor.stream.close();
        return createPage(document, font, "报告续页");
    }

    /** 在每页底部绘制页码和淡色底线。 */
    private void drawFooter(PDPageContentStream stream, PDFont font, int pageNumber) throws IOException {
        stream.setStrokingColor(new Color(203, 213, 224));
        stream.moveTo(MARGIN, 38F);
        stream.lineTo(PAGE_WIDTH - MARGIN, 38F);
        stream.stroke();
        writeText(stream, font, new Color(113, 128, 150), 9F, PAGE_WIDTH - MARGIN - 42F, 23F, "第 " + pageNumber + " 页");
    }

    /** 在指定位置写入单行文字并恢复正常绘制状态。 */
    private void writeText(PDPageContentStream stream, PDFont font, Color color, float size, float x, float y, String text) throws IOException {
        stream.setNonStrokingColor(color);
        stream.beginText();
        stream.setFont(font, size);
        stream.newLineAtOffset(x, y);
        stream.showText(text);
        stream.endText();
    }

    /** 将内部字段名转换为面向用户的中文标签。 */
    private String displayName(String field) {
        return switch (field) {
            case "overallScore" -> "综合评分";
            case "contentScore" -> "内容完整度";
            case "structureScore" -> "结构清晰度";
            case "skillMatchScore" -> "岗位匹配度";
            case "expressionScore" -> "表达质量";
            case "projectScore" -> "项目经历";
            case "summary" -> "总结";
            case "strengths" -> "优势";
            case "suggestions" -> "改进建议";
            case "issues" -> "待改进问题";
            case "technicalStack" -> "技术栈";
            case "technicalDepth" -> "技术深度";
            case "careerPreferences" -> "职业偏好";
            case "session" -> "面试概览";
            case "turns" -> "面试记录";
            default -> field;
        };
    }

    /** 保存当前页面输出流、页码和纵向绘制位置。 */
    private static final class PdfCursor {
        private final PDPageContentStream stream;
        private final int pageNumber;
        private float y;

        private PdfCursor(PDPageContentStream stream, int pageNumber, float y) {
            this.stream = stream;
            this.pageNumber = pageNumber;
            this.y = y;
        }
    }
}
