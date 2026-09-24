import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType0Font;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * 知识库 PDF 批量生成器。
 *
 * 每个文档的每个章节独立成页，
 * 保证导入后按页切分能产出多个 chunk。
 *
 * 运行：
 *   javac -encoding UTF-8 -cp "<依赖classpath>" GenPdfs.java
 *   java  -cp ".;<依赖classpath>" GenPdfs <输出目录>
 */
public class GenPdfs {

    record Section(String title, String body) {}

    record Doc(String fileName, String title, List<Section> sections) {}

    static final float MARGIN = 50f;
    static final float PAGE_W = PDRectangle.A4.getWidth();
    static final float PAGE_H = PDRectangle.A4.getHeight();
    static final int CHARS_PER_LINE = 38;

    public static void main(String[] args) throws Exception {

        String outDir = args[0];
        String fontPath = "C:/Windows/Fonts/simhei.ttf";

        for (Doc doc : buildDocs()) {
            generate(doc, fontPath, outDir);
            System.out.println("生成 " + doc.fileName());
        }
    }

    static void generate(Doc doc, String fontPath, String outDir)
            throws Exception {

        try (PDDocument pdf = new PDDocument()) {

            /*
             * 字体必须加载到各自的 PDDocument 中，
             * 不能跨文档复用。
             */
            PDType0Font font = PDType0Font.load(
                    pdf,
                    new java.io.FileInputStream(fontPath),
                    true
            );

            // 第一页：文档标题
            PDPage titlePage = newPage(pdf, font);
            writeLine(pdf, font, titlePage, doc.title(), 18f, MARGIN, PAGE_H - MARGIN - 12f);

            // 每个章节独立成页
            for (Section section : doc.sections()) {

                PDPage page = newPage(pdf, font);

                float y = PAGE_H - MARGIN - 20f;
                y = writeLine(pdf, font, page, section.title(), 14f, MARGIN, y);

                y -= 8f;

                for (String paragraph : section.body().split("\n")) {

                    if (paragraph.isBlank()) {
                        y -= 10f;
                        continue;
                    }

                    for (String line : wrap(paragraph.trim(), CHARS_PER_LINE)) {
                        y = writeLine(pdf, font, page, line, 12f, MARGIN, y);
                    }

                    y -= 8f;
                }
            }

            pdf.save(outDir + File.separator + doc.fileName());
        }
    }

    static PDPage newPage(PDDocument pdf, PDType0Font font) {
        PDPage page = new PDPage(PDRectangle.A4);
        pdf.addPage(page);
        return page;
    }

    static float writeLine(
            PDDocument pdf, PDType0Font font, PDPage page,
            String text, float size, float x, float y) throws Exception {

        try (PDPageContentStream cs = new PDPageContentStream(
                pdf, page,
                PDPageContentStream.AppendMode.APPEND, true, true)) {

            cs.beginText();
            cs.setFont(font, size);
            cs.newLineAtOffset(x, y);
            cs.showText(text);
            cs.endText();
        }

        return y - size - 6f;
    }

    static List<String> wrap(String text, int width) {

        List<String> lines = new ArrayList<>();

        for (int i = 0; i < text.length(); i += width) {
            lines.add(text.substring(i, Math.min(text.length(), i + width)));
        }

        return lines;
    }

    static List<Doc> buildDocs() {

        List<Doc> docs = new ArrayList<>();

        // ============ 计算机组成原理基础 ============

        List<Section> cst = new ArrayList<>();
        cst.add(new Section("第一章 计算机组成结构", """
                计算机由运算器、控制器、存储器、输入设备和输出设备五大部分组成。

                冯诺依曼架构的核心思想是存储程序：指令和数据以二进制形式存放在同一存储器中，计算机按地址顺序自动取出指令并执行。

                控制器负责从内存取出指令、译码并发出控制信号，运算器负责算术运算和逻辑运算，二者合称中央处理器 CPU。"""));
        cst.add(new Section("第二章 CPU 与指令执行", """
                一条指令的执行分为取指、译码、执行、写回四个阶段，程序计数器 PC 记录下一条指令的地址。

                指令流水线让多条指令的不同阶段并行执行，从而提高 CPU 吞吐率；分支预测失败会导致流水线清空，因此分支密集的代码性能更差。

                超标量处理器在一个时钟周期内发射多条指令，乱序执行则在不破坏依赖关系的前提下重排指令以提高并行度。"""));
        cst.add(new Section("第三章 存储层次结构", """
                存储体系从快到慢依次是寄存器、L1/L2/L3 高速缓存、内存和磁盘，越靠近 CPU 速度越快、容量越小、单位成本越高。

                缓存有效的基础是局部性原理：时间局部性指刚被访问的数据大概率再次被访问，空间局部性指相邻地址的数据大概率被一起访问。

                顺序读磁盘和内存访问的性能差距远小于随机读，这也是数据库顺序写日志、索引按页组织的重要依据。"""));
        cst.add(new Section("第四章 总线与 IO", """
                总线是连接计算机部件的公共通信干线，分为数据总线、地址总线和控制总线。

                中断机制让 CPU 不必轮询外设：外设就绪后向 CPU 发出中断信号，CPU 暂停当前程序转去执行中断处理程序。

                DMA 允许外设与内存直接交换数据而不经过 CPU，大幅降低了大块数据传输对 CPU 的占用。"""));
        docs.add(new Doc("计算机组成原理基础.pdf", "计算机组成原理基础", cst));

        // ============ 信息安全基础 ============

        List<Section> sec = new ArrayList<>();
        sec.add(new Section("第一章 密码学基础", """
                对称加密使用同一个密钥加密和解密，典型算法是 AES，速度快，适合加密大块数据，难点是密钥的安全分发。

                非对称加密使用公钥和私钥两个密钥，典型算法是 RSA 和椭圆曲线加密，公钥可以公开分发，私钥必须严格保密。

                实践中通常采用混合加密：用非对称加密协商对称密钥，之后的数据传输使用对称加密，HTTPS 正是这一方案。"""));
        sec.add(new Section("第二章 哈希与数字签名", """
                哈希函数把任意长度输入映射为固定长度输出，具有单向性和抗碰撞性。MD5 和 SHA-1 已被证明不安全，应使用 SHA-256 及以上算法。

                数字签名的过程是发送方用私钥对内容摘要签名，接收方用公钥验证，从而保证完整性和不可抵赖性。

                数字证书由 CA 签发，将公钥与持有者身份绑定，是 HTTPS 信任体系的基础。"""));
        sec.add(new Section("第三章 常见 Web 攻击与防御", """
                SQL 注入通过在输入中拼接 SQL 片段篡改查询语义，防御的核心是使用参数化查询和预编译语句，并对输入做校验。

                XSS 跨站脚本攻击把恶意脚本注入页面在用户浏览器执行，防御手段包括输出转义、内容安全策略 CSP 和 HttpOnly Cookie。

                CSRF 跨站请求伪造借用用户已登录的身份发起非法请求，常用防御是 CSRF Token 和 SameSite Cookie 属性。"""));
        sec.add(new Section("第四章 认证与授权", """
                认证解决你是谁的问题，授权解决你能做什么的问题，两者相互独立。

                JWT 由头部、载荷和签名三部分组成，服务端验证签名即可信任载荷，适合无状态的分布式场景，但签发后无法主动作废，需要配合黑名单或短有效期。

                密码绝不能明文存储，应使用 bcrypt、Argon2 等慢哈希加盐处理，即使数据库泄露也难以还原原始密码。"""));
        docs.add(new Doc("信息安全基础.pdf", "信息安全基础", sec));

        // ============ 数据结构与算法基础 ============

        List<Section> dsa = new ArrayList<>();
        dsa.add(new Section("第一章 线性结构", """
                数组支持随机访问，按下标读取是 O(1)，但插入和删除需要移动元素，平均是 O(n)。

                链表通过指针连接节点，插入删除只需修改指针，是 O(1)，但访问第 n 个元素必须从头遍历。

                栈是后进先出的结构，支持函数调用栈、括号匹配、表达式求值等场景；队列是先进先出的结构，广泛用于任务调度和消息缓冲。"""));
        dsa.add(new Section("第二章 树结构", """
                二叉搜索树左子树小于根、右子树大于根，查找平均 O(log n)，退化成链表时变成 O(n)。

                AVL 树通过严格平衡保证高度，红黑树用近似平衡换取更少的调整次数，是 Java HashMap 和 TreeMap 的底层结构之一。

                B+ 树是多路平衡搜索树，树高更低，一个节点对应磁盘一页，能显著减少磁盘 IO，是 MySQL 索引的标准实现。

                堆是完全二叉树，可以在 O(1) 取最值、O(log n) 插入和调整，是优先队列的底层实现。"""));
        dsa.add(new Section("第三章 排序算法", """
                冒泡、插入、选择排序的时间复杂度是 O(n^2)，适合小规模或基本有序的数据。

                归并排序稳定且最坏情况仍是 O(n log n)，但需要额外空间；快速排序平均性能最好，最坏退化为 O(n^2)，随机选取基准可以降低退化概率。

                堆排序空间复杂度为 O(1) 但不稳定；计数排序和桶排序在数据范围有限的场景可以达到线性时间。

                稳定排序保证相等元素的相对顺序不变，多字段排序时非常关键。"""));
        dsa.add(new Section("第四章 复杂度分析", """
                大 O 表示法描述算法耗时随规模增长的趋势，忽略常数和低阶项。

                常见复杂度从低到高：O(1)、O(log n)、O(n)、O(n log n)、O(n^2)、O(2^n)。二分查找是 O(log n)，哈希表平均查找是 O(1)。

                分析算法时要关注最坏、平均和最好情况的差异，同时权衡时间与空间，例如用哈希表换空间把两层循环降为一次遍历。"""));
        docs.add(new Doc("数据结构与算法基础.pdf", "数据结构与算法基础", dsa));

        // ============ 云计算与虚拟化 ============

        List<Section> cloud = new ArrayList<>();
        cloud.add(new Section("第一章 虚拟化技术", """
                虚拟化通过 Hypervisor 把物理资源抽象成多台虚拟机，每台虚拟机拥有独立的操作系统内核。

                类型一 Hypervisor 直接运行在硬件上，性能更好，常见于数据中心；类型二 Hypervisor 运行在宿主操作系统上，常见于个人桌面。

                虚拟化带来资源隔离、快照、热迁移等能力，是云计算资源池化的技术基础。"""));
        cloud.add(new Section("第二章 容器与虚拟机对比", """
                容器共享宿主机内核，只打包应用及其依赖，镜像体积通常只有几十 MB，启动是秒级；虚拟机独占内核，镜像以 GB 计，启动是分钟级。

                Linux 容器依赖 Namespace 实现隔离、Cgroups 实现资源限制，本质上是被隔离和受限的进程。

                容器适合微服务和弹性伸缩场景，虚拟机适合需要强隔离或异构操作系统的场景，两者可以结合使用。"""));
        cloud.add(new Section("第三章 云服务模型", """
                IaaS 提供虚拟机、存储和网络等基础资源，用户管理操作系统及以上层，例如云主机和云盘。

                PaaS 提供应用运行环境和中间件，用户只需部署代码，例如托管数据库和容器服务。

                SaaS 直接提供完整软件，用户开箱即用，例如在线办公套件。

                三种模型的分层越高，用户管理的部分越少，灵活度也越低，选择时需要在控制力和运维成本之间权衡。"""));
        cloud.add(new Section("第四章 Serverless 与弹性伸缩", """
                Serverless 把服务器管理完全交给云平台，开发者以函数为单位部署代码，平台按请求次数和执行时长计费。

                FaaS 平台在请求到来时拉起实例，长时间没有流量会释放实例，再次调用时的冷启动会带来额外延迟。

                Serverless 适合事件驱动、流量波动大的场景，例如定时任务、文件处理和轻量 API；长时间高并发的常驻服务使用容器或虚拟机往往更经济。

                弹性伸缩根据负载指标自动调整实例数量，配合无状态设计可以同时兼顾成本与可用性。"""));
        docs.add(new Doc("云计算与虚拟化.pdf", "云计算与虚拟化", cloud));

        return docs;
    }
}
