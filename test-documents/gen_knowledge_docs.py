# -*- coding: utf-8 -*-
"""
知识库扩充文档批量生成器（输出到 knowledge/ 目录）：

- 4 个 DOCX（OOXML 手工构造，含 Heading1/Heading2 标题样式引用 + 表格）
- 4 个 TXT（UTF-8 纯文本，篇幅保证切分出多个 chunk）
- 4 个 HTML（含 h1/h2 标题、表格、部分不闭合标签）

运行：python gen_knowledge_docs.py
"""

from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "knowledge"


# ==================== DOCX ====================

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para(text, style=None):
    text = esc(text)
    if style:
        return (f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
                f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>')
    return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def table(rows):
    body = "<w:tbl><w:tblPr><w:tblBorders>" \
           '<w:top w:val="single"/><w:left w:val="single"/>' \
           '<w:bottom w:val="single"/><w:right w:val="single"/>' \
           "</w:tblBorders></w:tblPr>"
    for row in rows:
        body += "<w:tr>" + "".join(
            f'<w:tc><w:p><w:r><w:t>{esc(c)}</w:t></w:r></w:p></w:tc>'
            for c in row) + "</w:tr>"
    return body + "</w:tbl>"


def build_docx(path, elements):
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(elements) + "<w:sectPr/></w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    import zipfile
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)


def docx_restful():
    e = []
    e.append(para("RESTful API 设计规范", style="Heading1"))
    e.append(para("REST 是一种基于 HTTP 协议的接口设计风格，核心思想是把服务端能力抽象为资源，通过统一的 HTTP 方法表达对资源的操作。"))
    e.append(para("资源命名", style="Heading2"))
    e.append(para("资源路径使用名词复数形式，例如 /users 表示用户集合，/users/123 表示标识为 123 的单个用户。"))
    e.append(para("路径全部使用小写字母，多个单词用中划线连接，避免使用下划线和驼峰。层级不宜超过两层，例如 /users/123/orders 表示用户的订单集合。"))
    e.append(para("HTTP 方法语义", style="Heading2"))
    e.append(para("GET 用于读取资源，POST 用于创建资源，PUT 用于全量更新，PATCH 用于部分更新，DELETE 用于删除资源。"))
    e.append(para("幂等性指同一请求执行多次与执行一次的效果相同。GET、PUT、DELETE 是幂等的，POST 不是幂等的，因此 POST 请求需要考虑重复提交问题。"))
    e.append(table([
        ["方法", "语义", "幂等", "安全"],
        ["GET", "读取资源", "是", "是"],
        ["POST", "创建资源", "否", "否"],
        ["PUT", "全量更新", "是", "否"],
        ["PATCH", "部分更新", "否", "否"],
        ["DELETE", "删除资源", "是", "否"],
    ]))
    e.append(para("状态码使用", style="Heading2"))
    e.append(para("成功场景：200 表示请求成功，201 表示创建成功，204 表示成功但无返回内容。"))
    e.append(para("客户端错误：400 表示参数错误，401 表示未认证，403 表示无权限，404 表示资源不存在，409 表示资源冲突，429 表示请求过于频繁。服务端错误统一使用 500 系列并在日志中记录详情。"))
    e.append(para("错误响应体应包含错误码、错误描述和追踪 ID，便于客户端处理和服务端排查。"))
    e.append(para("版本控制与分页", style="Heading2"))
    e.append(para("接口版本放在 URL 路径中，例如 /api/v1/users，大版本升级时并行提供旧版本并设置下线期限。"))
    e.append(para("集合接口必须分页，常用 page 加 size 的偏移分页，数据量大时使用基于游标的分页避免深分页性能问题，同时支持 sort 和 filter 参数。"))
    return e


def docx_database_design():
    e = []
    e.append(para("数据库设计规范", style="Heading1"))
    e.append(para("良好的数据库设计规范能减少后期的维护成本，避免命名混乱、字段滥用和性能陷阱。"))
    e.append(para("命名规范", style="Heading2"))
    e.append(para("表名和字段名使用小写加下划线的形式，表名使用名词，字段名避免使用数据库保留字。"))
    e.append(para("布尔字段使用 is_ 前缀，时间字段统一使用 _time 或 _date 后缀，所有表必须包含 create_time 和 update_time。"))
    e.append(para("三大范式", style="Heading2"))
    e.append(para("第一范式要求字段不可再分；第二范式要求非主键字段完全依赖主键，消除部分依赖；第三范式要求非主键字段之间没有传递依赖。"))
    e.append(para("范式化减少冗余，但查询需要更多关联。报表等读多写少的场景可以适当反范式化，用冗余换取查询性能，但必须保证冗余字段的一致性。"))
    e.append(para("索引设计", style="Heading2"))
    e.append(para("主键优先使用自增整数，分布式场景可以采用雪花算法等趋势递增的方案，避免使用随机字符串主键导致页分裂。"))
    e.append(para("联合索引遵循最左匹配原则，把区分度高的列放在前面；经常作为查询条件和排序列的字段应建立索引，但索引数量不宜过多，每个索引都会降低写入性能。"))
    e.append(table([
        ["索引类型", "适用场景"],
        ["BTREE", "等值查询、范围查询、排序，最常用"],
        ["HASH", "只有等值查询的场景，不支持范围"],
        ["FULLTEXT", "文本关键词搜索"],
    ]))
    e.append(para("字段设计", style="Heading2"))
    e.append(para("金额字段必须使用 DECIMAL 而不是 FLOAT 或 DOUBLE，避免浮点误差；状态字段使用 TINYINT 配合字典表；时间字段使用 DATETIME 或 TIMESTAMP 并注意时区。"))
    e.append(para("大字段和 JSON 字段会拖慢整行读取，应拆分到扩展表或单独存储，避免 SELECT * 拖出大字段。"))
    return e


def docx_microservice_comm():
    e = []
    e.append(para("微服务通信方式", style="Heading1"))
    e.append(para("微服务之间的通信方式决定了系统的耦合度、性能上限和一致性语义，是微服务架构设计的核心决策之一。"))
    e.append(para("同步通信", style="Heading2"))
    e.append(para("REST 基于 HTTP 和 JSON，简单通用、调试方便，适合对外接口和一般内部调用。"))
    e.append(para("gRPC 基于 HTTP/2 和 Protobuf，序列化体积小、性能高，支持流式通信，配合代码生成可以保证接口类型安全，适合内部高性能调用。"))
    e.append(para("同步调用必须设置合理的超时时间，配合重试、熔断和舱壁隔离，防止一个慢服务拖垮整条调用链。"))
    e.append(para("异步通信", style="Heading2"))
    e.append(para("消息队列把请求写入消息后立即返回，消费方异步处理，实现解耦、削峰和最终一致性。"))
    e.append(para("事件驱动架构中服务通过发布订阅协作，生产者不需要知道消费者是谁，扩展新的消费者不需要修改生产者。"))
    e.append(table([
        ["方式", "耦合度", "性能", "一致性", "适用场景"],
        ["REST", "松耦合", "中", "强一致", "对外接口、简单调用"],
        ["gRPC", "较紧", "高", "强一致", "内部高性能调用"],
        ["消息队列", "解耦", "高", "最终一致", "削峰、异步任务、事件广播"],
    ]))
    e.append(para("服务发现与容错", style="Heading2"))
    e.append(para("服务实例动态变化，调用方通过注册中心获取可用实例列表，结合客户端负载均衡选择节点。"))
    e.append(para("熔断器在错误率超阈值时快速失败，避免雪崩；降级在依赖不可用时返回兜底数据；限流保护服务不被突发流量压垮。"))
    return e


def docx_cache_pattern():
    e = []
    e.append(para("缓存设计模式", style="Heading1"))
    e.append(para("缓存是提升读性能最直接的手段，但引入缓存的同时也引入了数据一致性和复杂度问题，选择合适的缓存模式非常重要。"))
    e.append(para("Cache-Aside 模式", style="Heading2"))
    e.append(para("读请求先查缓存，命中直接返回；未命中查数据库，结果写入缓存后返回。"))
    e.append(para("写请求先更新数据库，再删除缓存。先更新数据库再删缓存，是大多数场景下最稳妥的选择，因为它把不一致窗口压缩到了最小。"))
    e.append(para("Read-Through 与 Write-Through", style="Heading2"))
    e.append(para("Read-Through 模式下应用只和缓存交互，缓存未命中时由缓存服务自己回源数据库，对应用屏蔽了回源逻辑。"))
    e.append(para("Write-Through 模式下写请求先写缓存，缓存同步写数据库，一致性更强但写入延迟更高。"))
    e.append(para("Write-Behind 模式", style="Heading2"))
    e.append(para("写请求只写缓存，缓存异步批量回写数据库，写入性能最好，但缓存宕机可能丢失数据，适合可以容忍丢失的场景，例如浏览计数。"))
    e.append(table([
        ["模式", "一致性", "写性能", "复杂度", "风险"],
        ["Cache-Aside", "最终一致", "高", "低", "短暂不一致"],
        ["Read/Write-Through", "强一致", "中", "中", "缓存层依赖重"],
        ["Write-Behind", "弱", "最高", "高", "可能丢数据"],
    ]))
    e.append(para("多级缓存", style="Heading2"))
    e.append(para("本地缓存访问最快但容量有限且多实例间不一致，分布式缓存全局一致但有网络开销，两者组成多级缓存可以兼顾性能与容量。"))
    e.append(para("本地缓存的失效通常通过消息广播完成：数据变更时广播失效消息，各实例删除对应的本地缓存条目。"))
    return e


# ==================== TXT ====================

TXT_LINUX = """Linux 常用命令

文件与目录操作

ls 列出目录内容，常用参数 -l 显示详情，-a 显示隐藏文件，-h 以人类可读方式显示大小。

cp 复制文件或目录，复制目录需要加 -r 参数；mv 既可以移动文件也可以重命名；rm 删除文件，删除目录需要 -r，加上 -f 表示不提示确认，使用时务必确认路径，避免误删。

find 按条件查找文件，例如 find . -name "*.log" 查找当前目录下所有日志文件，配合 -mtime 可以按修改时间过滤。

文本处理命令

cat 查看文件全部内容，less 分页查看大文件，head 和 tail 查看文件开头和结尾，tail -f 可以实时追踪日志文件的新增内容。

grep 用于文本搜索，-i 表示忽略大小写，-n 显示行号，-r 递归搜索目录，配合管道可以过滤任意命令的输出，例如 grep ERROR app.log 快速定位错误日志。

awk 按列处理文本，默认以空格分列，$1 表示第一列；sed 用于流编辑，常见用法是批量替换，例如 sed "s/old/new/g" 替换文本中的旧字符串。

进程管理命令

ps 查看进程快照，ps -ef 查看全量进程，配合 grep 过滤目标进程；top 交互式查看进程的资源占用，按 CPU 和内存排序。

kill 向进程发送信号，默认发送 SIGTERM 优雅终止，kill -9 发送 SIGKILL 强制杀死进程，应优先使用默认信号给进程清理资源的机会。

nohup 命令让进程在后台运行并且不随终端退出而终止，输出重定向到 nohup.out 文件。

网络与磁盘命令

curl 用于发起 HTTP 请求，-v 显示详细过程，-X 指定请求方法，-H 添加请求头，-d 发送请求体，是接口调试最常用的工具。

ping 测试网络连通性，telnet 或 nc 测试端口是否可达，ss -tlnp 查看端口监听状态，netstat 在旧系统上提供类似能力。

df -h 查看磁盘分区使用情况，du -sh 统计目录大小。排查磁盘写满问题时，先 df 定位分区，再用 du 逐层找到大文件。

权限管理命令

chmod 修改文件权限，权限分为属主、属组和其他人三组，每组有读、写、执行三种权限，例如 chmod 755 表示属主可读写执行、其他人可读和执行。

chown 修改文件属主和属组，目录的 x 权限表示可以进入目录。日常操作应避免使用 777 权限，遵循最小权限原则。
"""

TXT_GIT = """Git 协作流程

分支模型

主分支 main 保持随时可发布的状态，每次合入都应通过完整测试并打上版本标签。

功能开发在 feature 分支上进行，分支从 main 拉出，命名建议使用 feature/ 前缀加简短描述，例如 feature/user-login，开发完成并通过代码评审后合回主干。

多环境协作可以引入 develop 集成分支，也可以采用 trunk-based 模式用短生命周期分支加开关控制，团队规模和发布节奏决定选择。

提交规范

提交信息建议采用 Conventional Commits 格式：类型加冒号加描述，常见类型包括 feat 新功能、fix 修复缺陷、docs 文档、refactor 重构、test 测试、chore 构建。

一次提交只做一件事，提交粒度小而完整，便于回滚和问题定位。提交前使用 git diff 仔细检查改动，避免调试代码和无关文件混入。

合并与变基

git merge 把分支历史合并到当前分支，产生一个合并提交，保留真实的开发轨迹。

git rebase 把当前分支的提交搬到目标分支之后，历史线性干净，但会改写提交。原则是：共享分支使用 merge，私有分支合入前可以先 rebase 整理提交。

冲突处理

冲突发生时 git 会标记冲突文件，打开文件搜索冲突标记，结合业务意图手工合并后，git add 标记冲突已解决，最后完成合并或继续变基。

解决冲突前先理解两边的改动意图，不要盲目选择保留某一边，必要时找改动作者确认。

常用技巧

git stash 临时保存未完成的改动，切换分支处理紧急问题后再恢复；git cherry-pick 把指定提交摘取到当前分支，常用于把修复同步到发布分支。

git revert 生成一个反向提交来撤销某次改动，适合已经推送的公共分支；git reset 直接移动分支指针，--soft 保留改动在暂存区，--hard 彻底丢弃，只建议在私有分支使用。

发布时使用 git tag 打上语义化版本标签，配合变更日志记录每个版本的功能与修复。
"""

TXT_REGEX = """正则表达式基础

元字符与字符类

正则表达式是描述字符串模式的语言。点号匹配任意单个字符，星号表示前一个元素出现零次或多次，加号表示一次或多次，问号表示零次或一次。

方括号定义字符集合，例如 [abc] 匹配 a 或 b 或 c，[0-9] 匹配任意数字，[^0-9] 通过脱字符取反。常用简写包括 \\d 匹配数字、\\w 匹配字母数字下划线、\\s 匹配空白字符。

锚点中，脱字符匹配行首，美元符号匹配行尾，\\b 匹配单词边界。竖线表示或关系，圆括号用于分组。

贪婪与懒惰匹配

量词默认是贪婪的，尽可能多地匹配文本。在量词后加问号变为懒惰模式，尽可能少地匹配。

例如对 HTML 文本，<.*> 会贪婪匹配到整个标签串的最后一个尖括号，而 <.*?> 会懒惰匹配到第一个尖括号结束。处理结构化文本时应优先考虑懒惰匹配。

分组与引用

圆括号包裹的部分形成捕获组，可以按顺序编号引用，很多引擎支持命名分组，写法如 (?P<year>\\d{4})，按名称取值更易维护。

反向引用 \\1 在模式中重复匹配第一组捕获的内容，常用于匹配成对出现的引号或标签。

零宽断言

零宽断言只判断位置而不消耗字符。正向先行断言 (?=...) 要求后面匹配指定模式，负向先行断言 (?!...) 要求后面不匹配。

例如 \\d+(?=元) 匹配后面跟着元字的数字，而把元字排除在结果之外，提取文本中的数字时非常有用。

常见用例

手机号校验：^1[3-9]\\d{9}$，限定 1 开头第二位 3 到 9 共 11 位数字。

邮箱提取：[\\w.+-]+@[\\w-]+\\.[\\w.]+，结构上分为本地部分、@ 符号和域名部分。

日志提取：用分组捕获时间戳、级别和消息，例如 ^(\\S+) (\\S+) (\\S+): 提取前三个字段，配合 awk 可以做轻量日志分析。

使用建议

正则表达式追求准确和可读的平衡，复杂正则应添加注释或拆分处理步骤。生产代码中优先使用语言内置的完整匹配校验，避免用正则解析 HTML 等嵌套结构，选择专用解析器更可靠。
"""

TXT_FRONTEND = """前端开发基础概念

HTML 语义化

HTML 负责页面的结构和内容。语义化标签包括 header、nav、main、article、section、footer 等，使用语义化标签可以提升可访问性，也利于搜索引擎理解页面结构。

CSS 样式体系

盒模型把每个元素看作内容、内边距、边框和外边距的组合，box-sizing 设为 border-box 时宽度计算包含内边距和边框，布局更直观。

选择器优先级从高到低大致是行内样式、ID 选择器、类选择器、标签选择器，!important 可以强制提升优先级但应慎用。

Flex 布局适合一维排列，通过 justify-content 和 align-items 控制主轴与交叉轴对齐；Grid 布局适合二维网格，是复杂页面布局的首选。

JavaScript 核心概念

JavaScript 是单线程语言，通过事件循环实现异步。同步任务在主线程执行，异步任务完成后回调进入任务队列，宏任务与微任务按序调度，Promise 的 then 属于微任务。

闭包指函数与其词法作用域的组合，内部函数可以访问外部函数的变量，常用于封装私有状态，但不当使用可能造成内存泄漏。

原型是 JavaScript 实现继承的机制，每个对象都有原型，属性查找沿原型链向上进行。class 语法是原型继承的语法糖。

ES 模块化

现代前端使用 ES Module 组织代码，import 用于引入导出的绑定，支持静态分析，构建工具可以据此做摇树优化，移除未使用的代码。

框架与工程化

单页应用 SPA 在浏览器端动态渲染页面，前端路由切换视图，首屏加载和 SEO 需要服务端渲染或静态生成配合。

虚拟 DOM 在内存中先计算差异，再最小化更新真实 DOM，把开发者从手动操作 DOM 中解放出来。

组件化把页面拆分为可复用的组件，组件内部维护状态，状态变化驱动视图更新。跨组件的状态共享交给状态管理库，例如 Pinia 或 Redux。

构建工具负责依赖打包、代码转换和压缩优化，Vite 利用浏览器原生模块实现毫秒级冷启动，生产构建基于 Rollup；Webpack 生态最成熟，适合复杂定制。

性能优化关注点：图片懒加载、代码分割按需加载、静态资源缓存与压缩、减少重排重绘，用性能面板定位瓶颈后再优化。
"""


# ==================== HTML ====================

HTML_CACHE = """<!DOCTYPE html>
<html>
<head><title>HTTP 缓存机制</title></head>
<body>
<div class="doc">
  <h1>HTTP 缓存机制</h1>
  <p>HTTP 缓存通过在中间或客户端保存资源副本，减少重复的网络请求和服务器压力，是 Web 性能优化的第一道防线
  <div class="section">
    <h2>强缓存</h2>
    <p>强缓存由 Cache-Control 响应头控制，命中时浏览器直接使用本地副本，不会发起请求
    <p>常用指令：max-age 设置副本有效秒数，no-cache 表示可以使用但必须协商验证，no-store 表示完全不缓存，private 只允许浏览器缓存，public 允许中间代理缓存
    <p>Expires 是 HTTP/1.0 的旧头部，使用绝对时间，受客户端时钟影响，已被 Cache-Control 取代
  </div>
  <div class="section">
    <h2>协商缓存</h2>
    <p>强缓存过期后，浏览器发起条件请求向服务器验证副本是否仍然有效，有效则返回 304，浏览器继续使用本地副本
    <p>协商缓存有两组头：服务器返回 ETag 标识资源版本，浏览器下次通过 If-None-Match 携带该值；服务器返回 Last-Modified 修改时间，浏览器通过 If-Modified-Since 携带
    <p>ETag 优先级高于 Last-Modified，因为 ETag 能感知内容变化，而修改时间只精确到秒
  </div>
  <h2>常用头部速查</h2>
  <table>
    <tr><th>头部</th><th>方向</th><th>作用</th></tr>
    <tr><td>Cache-Control: max-age</td><td>响应</td><td>设置强缓存有效期</td></tr>
    <tr><td>ETag</td><td>响应</td><td>资源版本指纹</td></tr>
    <tr><td>If-None-Match</td><td>请求</td><td>携带 ETag 参与协商</td></tr>
    <tr><td>Last-Modified</td><td>响应</td><td>最后修改时间</td></tr>
  </table>
  <h2>缓存实践建议</h2>
  <p>带文件名指纹的静态资源可以设置超长强缓存，内容变更时更换文件名强制更新
  <p>HTML 入口页面建议使用 no-cache 走协商缓存，保证用户总能拿到最新的资源引用
</div>
</body>
</html>"""

HTML_K8S = """<!DOCTYPE html>
<html>
<head><title>Kubernetes 基础概念</title></head>
<body>
<h1>Kubernetes 基础概念</h1>
<p>Kubernetes 是容器编排平台，负责容器的部署、伸缩、自愈和滚动升级
<div class="intro">
  <h2>Pod</h2>
  <p>Pod 是最小的调度单元，一个 Pod 包含一个或多个共享网络和存储的容器
  <p>同一个 Pod 内的容器通过 localhost 互相访问，生命周期一致，适合强关联的边车模式
  <div class="detail">
    <h2>Deployment</h2>
    <p>Deployment 声明期望的副本数和镜像版本，控制器持续对比实际状态与期望状态，自动拉起失败的实例
    <p>滚动更新逐批替换旧实例，保证升级过程中服务不中断，异常时可以一键回滚到上一个版本
  </div>
</div>
<h2>核心对象速查</h2>
<table>
  <tr><th>对象</th><th>作用</th></tr>
  <tr><td>Pod</td><td>最小调度单元</td></tr>
  <tr><td>Deployment</td><td>管理副本与滚动更新</td></tr>
  <tr><td>Service</td><td>为一组 Pod 提供稳定访问入口</td></tr>
  <tr><td>ConfigMap</td><td>注入配置文件与环境变量</td></tr>
  <tr><td>Ingress</td><td>七层路由，把外部流量转发到 Service</td></tr>
</table>
<h2>Service 与网络</h2>
<p>Pod 的 IP 会随重建变化，Service 通过标签选择器关联一组 Pod 并提供固定的虚拟 IP 和 DNS 名称
<p>Service 类型中 ClusterIP 仅供集群内部访问，NodePort 在每个节点打开端口，LoadBalancer 对接云厂商负载均衡器
<p>控制面负责调度和决策，节点上的 kubelet 负责执行，二者配合实现声明式的容器编排
</body>
</html>"""

HTML_OBS = """<!DOCTYPE html>
<html>
<head><title>日志与可观测性</title></head>
<body>
<div class="wrap">
  <h1>日志与可观测性</h1>
  <p>可观测性通过系统对外输出的信号理解系统内部状态，三大支柱是日志、指标和链路追踪
  <div class="sec">
    <h2>日志</h2>
    <p>日志记录离散事件的详细信息，级别从低到高分为 DEBUG、INFO、WARN、ERROR，生产环境一般输出 INFO 及以上
    <p>日志规范要求：使用参数化占位符而不是字符串拼接、输出结构化 JSON 便于采集解析、每条链路日志携带 traceId 便于串联
    <p>采集链路通常是应用输出到标准输出，收集组件集中传输到 Elasticsearch 等存储，通过 Kibana 查询分析
  </div>
  <div class="sec">
    <h2>指标监控</h2>
    <p>指标是聚合的时间序列数值，适合观察趋势和触发告警，核心业务指标包括 QPS、响应时间分位数和错误率
    <p>响应时间要看 P95 和 P99 分位数而不是平均值，平均值会掩盖长尾请求的恶化
    <p>Prometheus 定时拉取应用暴露的指标端点，配合 Grafana 完成可视化面板
  </div>
  <h2>三大支柱对比</h2>
  <table>
    <tr><th>信号</th><th>数据形态</th><th>解决的问题</th></tr>
    <tr><td>日志</td><td>离散事件文本</td><td>问题定位与审计</td></tr>
    <tr><td>指标</td><td>聚合时间序列</td><td>趋势观察与告警</td></tr>
    <tr><td>链路追踪</td><td>调用链 Span</td><td>跨服务延迟分析</td></tr>
  </table>
  <div class="sec">
    <h2>链路追踪与告警</h2>
    <p>分布式链路追踪为每次请求生成全局 TraceId，每个服务内部的处理段记录为 Span，串联后可以还原完整调用路径并定位耗时瓶颈
    <p>告警设计要分级，致命告警电话或短信触达，重要告警进值班群，低优先级聚合为日报；同时配置告警抑制和静默窗口，避免告警风暴淹没真正的问题
  </div>
</div>
</body>
</html>"""

HTML_MQ = """<!DOCTYPE html>
<html>
<head><title>消息队列选型对比</title></head>
<body>
<h1>消息队列选型对比</h1>
<p>消息队列用于服务解耦、异步处理和流量削峰，不同产品在吞吐、延迟和功能特性上差异明显，选型要结合业务场景
<div class="s">
  <h2>RabbitMQ</h2>
  <p>基于 AMQP 协议，交换机和绑定规则提供灵活的路由能力，消息确认和死信机制完善
  <p>吞吐在万级到十万级，延迟低，适合业务消息和任务分发，百万级以上吞吐不是它的强项
</div>
<div class="s">
  <h2>Kafka</h2>
  <p>Kafka 把消息组织为分区的追加日志，顺序写磁盘加上零拷贝带来极高的吞吐，单集群可达百万级
  <p>消息按保留策略存储，支持按偏移量回溯消费，是日志采集、流式计算和数据管道的事实标准
  <p>Kafka 不支持单条延迟消息和丰富的路由语义，消费语义通过消费组位移管理实现
</div>
<h2>三者对比</h2>
<table>
  <tr><th>特性</th><th>RabbitMQ</th><th>Kafka</th><th>RocketMQ</th></tr>
  <tr><td>吞吐量</td><td>万级到十万级</td><td>百万级</td><td>十万级</td></tr>
  <tr><td>延迟</td><td>微秒到毫秒级</td><td>毫秒级</td><td>毫秒级</td></tr>
  <tr><td>消息回溯</td><td>不支持</td><td>支持</td><td>支持</td></tr>
  <tr><td>事务消息</td><td>弱</td><td>有限</td><td>原生支持</td></tr>
  <tr><td>典型场景</td><td>业务消息、任务分发</td><td>日志管道、流计算</td><td>电商交易、延迟消息</td></tr>
</table>
<div class="s">
  <h2>选型建议</h2>
  <p>追求低延迟和灵活路由选 RabbitMQ，超高吞吐和数据回溯选 Kafka，需要事务消息和延迟消息的电商场景优先 RocketMQ
  <p>选型之外更要关注使用规范：幂等消费、消息可观测、容量规划与过期策略，这些比产品差异更影响线上稳定性
</div>
</body>
</html>"""


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # DOCX
    build_docx(OUT_DIR / "RESTful API 设计规范.docx", docx_restful())
    build_docx(OUT_DIR / "数据库设计规范.docx", docx_database_design())
    build_docx(OUT_DIR / "微服务通信方式.docx", docx_microservice_comm())
    build_docx(OUT_DIR / "缓存设计模式.docx", docx_cache_pattern())
    print("生成 4 个 DOCX")

    # TXT
    (OUT_DIR / "Linux 常用命令.txt").write_text(TXT_LINUX, encoding="utf-8")
    (OUT_DIR / "Git 协作流程.txt").write_text(TXT_GIT, encoding="utf-8")
    (OUT_DIR / "正则表达式基础.txt").write_text(TXT_REGEX, encoding="utf-8")
    (OUT_DIR / "前端开发基础概念.txt").write_text(TXT_FRONTEND, encoding="utf-8")
    print("生成 4 个 TXT")

    # HTML
    (OUT_DIR / "HTTP 缓存机制.html").write_text(HTML_CACHE, encoding="utf-8")
    (OUT_DIR / "Kubernetes 基础概念.html").write_text(HTML_K8S, encoding="utf-8")
    (OUT_DIR / "日志与可观测性.html").write_text(HTML_OBS, encoding="utf-8")
    (OUT_DIR / "消息队列选型对比.html").write_text(HTML_MQ, encoding="utf-8")
    print("生成 4 个 HTML")


if __name__ == "__main__":
    main()
