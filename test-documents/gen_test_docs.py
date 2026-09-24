# -*- coding: utf-8 -*-
"""
生成不规则测试文档，用于验证知识库导入的容错能力：

1. 不规则测试文档.docx
   - 手工构造的最小 OOXML 包，没有任何 styles.xml
   - 段落引用未定义的样式 ID（Heading9 / 1）
   - 包含空段落、不规整表格、混合中英文正文
2. 软件测试补充.txt
   - GBK 编码（中文 Windows 常见导出编码），且为 CRLF 换行
3. 网络安全补充.html
   - 标签不闭合、div 混乱嵌套、缺少 charset 声明

运行：python gen_test_docs.py
"""

import zipfile
from pathlib import Path

OUT_DIR = Path(__file__).parent


def build_docx():
    """手工构造一个“不规则”的 docx。"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    def para(text, style=None):
        if style:
            return (
                f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
                f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
            )
        return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'

    def cell(text):
        return f'<w:tc><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:tc>'

    body = []
    body.append(para("WebSocket 与轮询技术补充知识"))
    body.append("<w:p/>")  # 空段落
    body.append(para("WebSocket 是一种在单个 TCP 连接上进行全双工通信的协议。浏览器和服务器只需要完成一次握手，两者之间就可以创建持久性的连接，并进行双向数据传输。"))
    body.append(para("与 WebSocket 不同，短轮询由客户端定时向服务器发起 HTTP 请求，无论是否有新数据都返回结果，实现简单但延迟高，且大量无效请求浪费服务器资源。"))
    body.append(para("长轮询是短轮询的改进版本。客户端发起请求后，服务器在有新数据时才响应，如果没有新数据则保持连接一段时间，超时后客户端重新发起请求。长轮询的实时性优于短轮询，但每次响应后仍需重新建立请求。"))
    # 引用未定义的样式 ID（文档中没有 styles.xml）
    body.append(para("轮询与 WebSocket 的对比", style="Heading9"))
    body.append(para("从实时性、服务器开销和实现复杂度三个维度对比，WebSocket 都明显优于轮询方案，是构建聊天、协作编辑、实时行情等应用的首选。", style="1"))
    body.append("<w:p><w:r/></w:p>")  # 只有无文本 Run 的段落

    table = (
        "<w:tbl><w:tblPr><w:tblBorders>"
        '<w:top w:val="single"/><w:left w:val="single"/>'
        '<w:bottom w:val="single"/><w:right w:val="single"/>'
        "</w:tblBorders></w:tblPr>"
        "<w:tr>"
        + cell("通信方式") + cell("实时性") + cell("服务器开销") + cell("适用场景")
        + "</w:tr>"
        "<w:tr>"
        + cell("短轮询") + cell("低") + cell("高，大量无效请求") + cell("数据更新频率很低的页面")
        + "</w:tr>"
        "<w:tr>"
        + cell("长轮询") + cell("中") + cell("中，连接保持时间较长") + cell("实时性要求一般的场景")
        + "</w:tr>"
        "<w:tr>"
        + cell("WebSocket") + cell("高") + cell("低，连接复用") + cell("聊天室、实时行情、在线协作")
        + "</w:tr>"
        "</w:tbl>"
    )
    body.append(table)
    body.append(para("选择建议：如果应用需要毫秒级的实时推送，优先选择 WebSocket；如果只是低频的状态检查，短轮询或长轮询的维护成本更低。"))

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + "<w:sectPr/></w:body></w:document>"
    )

    path = OUT_DIR / "不规则测试文档.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)

    print(f"生成 {path.name}")


def build_txt():
    """GBK 编码 + CRLF 换行的纯文本。"""

    text = (
        "软件测试补充知识\r\n"
        "\r\n"
        "测试金字塔从下到上分为三层：单元测试、接口测试、UI 测试。\r\n"
        "越靠近底层的测试数量应该越多，因为单元测试运行速度快、维护成本低，可以在开发阶段尽早发现缺陷。\r\n"
        "\r\n"
        "回归测试是在代码修改之后重新执行既有测试，确保原有功能没有被新改动破坏。\r\n"
        "在持续集成环境中，每次代码提交都会自动触发回归测试，快速反馈集成问题。\r\n"
        "\r\n"
        "缺陷生命周期包括：新建、确认、修复、回归验证、关闭几个状态。\r\n"
        "清晰的状态流转和优先级定义，是缺陷管理流程规范化的基础。\r\n"
    )

    path = OUT_DIR / "软件测试补充.txt"
    path.write_bytes(text.encode("gbk"))
    print(f"生成 {path.name}（GBK 编码）")


def build_html():
    """标签不闭合、嵌套混乱、缺少 charset 声明的 HTML。"""

    html = """<!DOCTYPE html>
<html>
<head>
<title>网络安全补充知识</title>
</head>
<body>
<div id="wrap">
  <h1>HTTPS 证书校验流程</h1>
  <div class="section">
    <p>客户端收到服务器证书后，会逐级校验证书链，确认证书由受信任的 CA 签发
    <p>证书校验包括签名验证、有效期检查、域名匹配和吊销状态查询四个步骤，任何一步失败都会终止握手并提示风险
    <div class="detail">
      <h2>证书链</h2>
      <p>服务器证书由中间 CA 签发，中间 CA 由根 CA 签发，浏览器使用内置的根证书库逐级验证签名
      <h2>域名匹配</h2>
      <p>证书中的 Subject Alternative Name 必须包含当前访问的域名，否则浏览器会提示证书域名不匹配
    </div>
  </div>
  <h2>HTTP 与 HTTPS 状态码对比</h2>
  <table>
    <tr><th>类别</th><th>含义</th><th>典型示例</th></tr>
    <tr><td>2xx</td><td>成功</td><td>200 请求成功</td></tr>
    <tr><td>4xx</td><td>客户端错误</td><td>401 未认证，403 禁止访问</td></tr>
    <tr><td>5xx</td><td>服务端错误</td><td>500 内部错误，502 网关错误</td></tr>
  </table>
  <p>生产环境建议全站启用 HTTPS，并配合 HSTS 强制浏览器使用加密连接
</div>
</body>
</html>"""

    path = OUT_DIR / "网络安全补充.html"
    path.write_text(html, encoding="utf-8")
    print(f"生成 {path.name}")


if __name__ == "__main__":
    build_docx()
    build_txt()
    build_html()
    print("全部测试文档生成完成。")
