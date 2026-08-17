"""公开网页读取与有限抓取实现。"""

import asyncio
import hashlib
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from agent.Common.Exceptions.agent_exception import ExternalWebContentUnsafeError, ExternalWebRequestError


class ArticleParser(HTMLParser):
    """以标准库提取普通技术网页的标题、正文块和链接，跳过脚本及导航等噪声区域。"""

    ignoredTags = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "form", "aside", "iframe"}
    blockTags = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "li", "pre", "blockquote", "br"}

    def __init__(self) -> None:
        """初始化 HTML 解析期间所需的标题、块文本、链接和忽略深度状态。"""
        super().__init__(convert_charrefs=True)
        self.titleParts: list[str] = []
        self.blocks: list[str] = []
        self.links: list[str] = []
        self.currentBlock: list[str] = []
        self.ignoredDepth = 0
        self.titleDepth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """记录正文结构与链接；进入不可读标签时暂停正文收集。"""
        lowered = tag.lower()
        values = dict(attrs)
        if lowered in self.ignoredTags:
            self.ignoredDepth += 1
            return
        if self.ignoredDepth:
            return
        if lowered == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if lowered == "title":
            self.titleDepth += 1
        if lowered in self.blockTags:
            self.flushBlock()
        if lowered.startswith("h") and len(lowered) == 2 and lowered[1].isdigit():
            self.currentBlock.append("#" * min(int(lowered[1]), 6) + " ")
        if lowered == "li":
            self.currentBlock.append("- ")

    def handle_endtag(self, tag: str) -> None:
        """在块元素结束时落盘正文，并在离开忽略标签后恢复提取。"""
        lowered = tag.lower()
        if lowered in self.ignoredTags and self.ignoredDepth:
            self.ignoredDepth -= 1
            return
        if self.ignoredDepth:
            return
        if lowered == "title" and self.titleDepth:
            self.titleDepth -= 1
        if lowered in self.blockTags:
            self.flushBlock()

    def handle_data(self, data: str) -> None:
        """清理浏览器文本节点的多余空白后追加到当前正文块。"""
        if self.ignoredDepth:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if not value:
            return
        if self.titleDepth:
            self.titleParts.append(value)
        self.currentBlock.append(value)

    def close(self) -> None:
        """结束解析时刷出最后一个未闭合的正文块。"""
        super().close()
        self.flushBlock()

    def flushBlock(self) -> None:
        """将当前累计文本转换为单个 Markdown 正文块，避免逐字节点造成噪声。"""
        content = " ".join(self.currentBlock).strip()
        if content:
            self.blocks.append(content)
        self.currentBlock = []


class NoRedirectHandler(HTTPRedirectHandler):
    """禁止 urllib 自动跳转，使每一级重定向地址都能先经过公开地址检查。"""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """返回空请求以把重定向响应交给 WebReader 的受控循环处理。"""
        return None


class WebReader:
    """只读取公开 HTTP(S) 页面，并在单页和站点抓取时施加可控边界。"""

    def __init__(self, maxBytes: int = 5 * 1024 * 1024, maxPages: int = 20, maxDepth: int = 2) -> None:
        """保存网页响应体、页面数量和抓取深度上限，防止网页工具无限占用资源。"""
        self.maxBytes = maxBytes
        self.maxPages = maxPages
        self.maxDepth = maxDepth

    async def fetchPage(self, url: str) -> dict[str, object]:
        """拉取一个公开 HTML 页面，提取标题与正文 Markdown，并返回规范化来源信息。"""
        normalizedUrl = self.validatePublicUrl(url)
        finalUrl, contentType, body = await asyncio.to_thread(self.requestPage, normalizedUrl)
        parser = ArticleParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        parser.close()
        title = " ".join(parser.titleParts).strip() or finalUrl
        markdown = (f"# {title}\n\n" + "\n\n".join(parser.blocks)).strip()
        return {
            "url": finalUrl,
            "title": title[:500],
            "contentType": contentType,
            "contentHash": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "markdown": markdown[:180000],
            "links": [self.normalizeUrl(link, finalUrl) for link in parser.links if self.normalizeUrl(link, finalUrl)],
        }

    async def crawlSite(self, entryUrl: str) -> dict[str, object]:
        """从入口页同域逐层读取有限数量页面，返回正文文档集合供知识库工作流后续入库。"""
        normalizedEntry = self.validatePublicUrl(entryUrl)
        host = urlparse(normalizedEntry).hostname
        queue: list[tuple[str, int, str | None]] = [(normalizedEntry, 0, None)]
        seen: set[str] = set()
        documents: list[dict[str, object]] = []
        rejected: list[dict[str, str]] = []
        while queue and len(documents) < self.maxPages:
            candidate, depth, parentUrl = queue.pop(0)
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                document = await self.fetchPage(candidate)
            except Exception as error:
                rejected.append({"url": candidate, "reason": str(error)[:200]})
                continue
            finalUrl = str(document["url"])
            if finalUrl in {str(item["url"]) for item in documents}:
                continue
            document["depth"] = depth
            document["parentUrl"] = parentUrl
            documents.append(document)
            if depth >= self.maxDepth:
                continue
            for link in document["links"]:
                if isinstance(link, str) and urlparse(link).hostname == host and link not in seen:
                    queue.append((link, depth + 1, finalUrl))
        return {
            "entryUrl": normalizedEntry,
            "documents": documents,
            "rejected": rejected,
            "completed": not queue,
        }

    def validatePublicUrl(self, value: str) -> str:
        """拒绝本地、私网和非 HTTP(S) 地址，避免网页工具被用于访问部署环境内部服务。"""
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ExternalWebContentUnsafeError("仅支持公开 http 或 https 地址")
        if parsed.username or parsed.password:
            raise ExternalWebContentUnsafeError("网页地址不能包含凭据")
        try:
            addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as error:
            raise ExternalWebRequestError("网页域名无法解析") from error
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified:
                raise ExternalWebContentUnsafeError("网页地址不能指向本地或私有网络")
        return parsed.geturl()

    def requestPage(self, url: str) -> tuple[str, str, bytes]:
        """执行受控重定向的同步 HTTP 读取；每一级地址都先检查，避免重定向绕过 SSRF 防护。"""
        currentUrl = url
        opener = build_opener(NoRedirectHandler())
        for _ in range(4):
            try:
                request = Request(currentUrl, headers={"User-Agent": "InterviewGuideAgent/1.0"})
                with opener.open(request, timeout=30) as response:
                    finalUrl = self.validatePublicUrl(response.geturl())
                    contentType = response.headers.get_content_type().lower()
                    if contentType not in {"text/html", "application/xhtml+xml"}:
                        raise ExternalWebContentUnsafeError("网页响应不是 HTML")
                    body = response.read(self.maxBytes + 1)
                    if len(body) > self.maxBytes:
                        raise ExternalWebContentUnsafeError("网页内容超过大小上限")
                    return finalUrl, contentType, body
            except HTTPError as error:
                location = error.headers.get("Location") if error.headers else None
                if error.code not in {301, 302, 303, 307, 308} or not location:
                    raise ExternalWebRequestError(f"网页请求失败：HTTP {error.code}") from error
                currentUrl = self.validatePublicUrl(urljoin(currentUrl, location))
            except ExternalWebContentUnsafeError:
                raise
            except Exception as error:
                raise ExternalWebRequestError(f"网页抓取失败：{error}") from error
        raise ExternalWebContentUnsafeError("网页重定向次数超过上限")

    def normalizeUrl(self, rawUrl: str, baseUrl: str) -> str | None:
        """将页面链接标准化为无片段的绝对 HTTP(S) 地址，供同域抓取去重使用。"""
        candidate = urljoin(baseUrl, rawUrl).strip()
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.params, parsed.query, ""))
