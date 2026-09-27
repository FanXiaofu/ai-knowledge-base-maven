# 人工评分表（裁判校准用）

- 时间：2026-09-27T23:58:07
- 样本：20 条
- 打分方式：在 `evaluation/judge/human_labels.json` 里填 `scores.faithfulness / relevancy / correctness`（1~5 的整数，>= 4 为通过）
- 独立评分：本表不含任何裁判分数，请勿参考 judge_scores.json，否则一致率失真

## 评分锚点

# 生成质量人工评分锚点（裁判校准用）

对照 `evaluation/judge/human_sheet.md` 逐题打分，把分数填进
`evaluation/judge/human_labels.json` 的 `scores` 字段（1~5 的整数）。

三维护，独立评判。**不要参考 `judge_scores.json`**——人工与裁判必须独立产生，
否则一致率没有意义。

## faithfulness（忠实度）

回答中的事实性陈述，是否都能在**给定的上下文片段**里找到依据。

| 分 | 判据 |
|---|---|
| 5 | 所有事实性陈述都能在片段中找到依据，无编造 |
| 4 | 基本有据，仅有个别无依据的引申 |
| 3 | 大体有据，但存在少量无依据的引申 |
| 2 | 有多处无依据的陈述 |
| 1 | 存在明显编造（关键结论在片段里查无实据） |

> 只用给定片段判断，不要用你自己掌握的知识给回答"补依据"。
> 回答若明确拒答（"知识库中没有足够的信息"），faithfulness 记 5。

## relevancy（切题度）

回答是否直接命中用户问题。

| 分 | 判据 |
|---|---|
| 5 | 完全切题，正面回答 |
| 4 | 基本切题，略有冗余 |
| 3 | 部分偏题或答得不够聚焦 |
| 2 | 大多偏离问题 |
| 1 | 答非所问 |

## correctness（正确性）

回答内容本身是否正确、完整。

| 分 | 判据 |
|---|---|
| 5 | 正确且完整 |
| 4 | 正确，略有缺漏 |
| 3 | 部分正确或有明显缺漏 |
| 2 | 大体不正确 |
| 1 | 明显错误 |

> 若该题有 `expected_points`（参考要点），以要点的覆盖情况为准。

## 打分习惯建议

- 先读问题，再只看**给定的上下文片段**判断 faithfulness，最后凭领域判断 correctness
- 分差 <= 1 视为"相邻一致"，因此不必纠结 4 还是 5；但 3 与 5 之间要区分清楚
- 拿不准的题在 `comment` 里写一句理由，校准报告会一并留痕

## 逐题

### [1] Redis分布式锁怎么实现

- 金标来源：redis.md
- 金标章节：Redis 分布式锁

**上下文片段**

```
[1] Redis中文文档-分布式锁.html — *为什么基于故障转移的实现还不够
*为什么基于故障转移的实现还不够

为了更好的理解我们想要改进的方面，我们先分析一下当前大多数基于Redis的分布式锁现状和实现方法.

实现Redis分布式锁的最简单的方法就是在Redis中创建一个key，这个key有一个失效时间（TTL)，以保证锁最终会被自动释放掉（这个对应特性2）。当客户端释放资源(解锁）的时候，会删除掉这个key。

从表面上看，似乎效果还不错，但是这里有一个问题：这个架构中存在一个严重的单点失败问题。如果Redis挂了怎么办？你可能会说，可以通过增加一个slave节点解决这个问题。但这通常是行不通的。这样做，我们不能实现资源的独享,因为Redis的主从同步通常是异步的。

在这种场景（主从结构）中存在明显的竞态:

客户端A从master获取到锁

在master将锁同步到slave之前，master宕掉了。

slave节点被晋级为master节点

客户端B取得了同一个资源被客户端A已经获取到的另外一个锁。安全失效！

有时候程序就是这么巧，比如说正好一个节点挂掉的时候，多个客户端同时取到了锁。如果你可以接受这种小概率错误，那用这个基于复制的方案就完全没有问题。否则的话，我们建议你实现下面描述的解决方案。

[2] redis.md — Redis 分布式锁
Redis 分布式锁

Redis 可以利用 SET 命令实现分布式锁。

分布式锁可以用于控制多个服务实例对共享资源的并发访问。

实现分布式锁时需要考虑锁的原子性、过期时间以及误删锁等问题。

[3] Redis中文文档-分布式锁.html — *单Redis实例实现分布式锁的正确方法
*单Redis实例实现分布式锁的正确方法

在尝试克服上述单实例设置的限制之前，让我们先讨论一下在这种简单情况下实现分布式锁的正确做法，实际上这是一种可行的方案，尽管存在竞态，结果仍然是可接受的，另外，这里讨论的单实例加锁方法也是分布式加锁算法的基础。

获取锁使用命令:

SET resource_name my_random_value NX PX 30000

这个命令仅在不存在key的时候才能被执行成功（NX选项），并且这个key有一个30秒的自动失效时间（PX属性）。这个key的值是"myrandomvalue"(一个随机值），这个值在所有的客户端必须是唯一的，所有同一key的获取者（竞争者）这个值都不能一样。

value的值必须是随机数主要是为了更安全的释放锁，释放锁的时候使用脚本告诉Redis:只有key存在并且存储的值和我指定的值一样才能告诉我删除成功。可以通过以下Lua脚本实现：

if redis.call("get",KEYS[1]) == ARGV[1] then
    return redis.call("del",KEYS[1])
else
    return 0
end

使用这种方式释放锁可以避免删除别的客户端获取成功的锁。举个例子：客户端A取得资源锁，但是紧接着被一个其他操作阻塞了，当客户端A运行完毕其他操作后要释放锁时，原来的锁早已超时并且被Redis自动释放，并且在这期间资源锁又被客户端B再次获取到。如果仅使用DEL命令将key删除，那么这种情况就会把客户端B的锁给删除掉。使用Lua脚本就不会存在这种情况，因为脚本仅会删除value等于客户端A的value的key（value相当于客户端的一个签名）。

这个随机字符串应该怎么设置？我认为它应该是从/dev/urandom产生的一个20字节随机数，但是我想你可以找到比这种方法代价更小的方法，只要这个数在你的任务中是唯一的就行。例如一种安全可行的方法是使用/dev/urandom作为RC4的种子和源产生一个伪随机流;一种更简单的方法是把以毫秒为单位的unix时间和客户端ID拼接起来，理论上不是完全安全，但是在多数情况下可以满足需求.
```

**回答**

```
Redis分布式锁的实现方法：Redis可以利用SET命令实现分布式锁。[2] 具体步骤为：获取锁使用命令 `SET resource_name my_random_value NX PX 30000`（`my_random_value`需唯一，如时间戳和客户端ID拼接），释放锁时使用Lua脚本安全删除锁以避免误删。[3]

参考来源：
[1] Redis中文文档-分布式锁.html — *为什么基于故障转移的实现还不够
[2] redis.md — Redis 分布式锁
[3] Redis中文文档-分布式锁.html — *单Redis实例实现分布式锁的正确方法
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [2] Redis缓存击穿怎么解决

- 金标来源：redis.md
- 金标章节：Redis 缓存击穿

**上下文片段**

```
[1] redis.md — Redis 缓存击穿
Redis 缓存击穿

缓存击穿通常发生在某个热点 Key 过期的瞬间，大量并发请求同时访问数据库。

常见解决方案包括：

- 互斥锁
- 逻辑过期
- 热点数据永不过期

[2] SpringBoot企业级后端开发技术手册.pdf — 第19页
图3 Redis缓存穿透/击穿/雪崩问题处理架构图
三类问题的定义、产生原因与解决方案如下表所示：
问题
类型
问题定义 产生原因 解决方案
缓存
穿透
查询数据库中不存在的数
据，缓存永远无法命中
恶意攻击、非法参数、
业务数据不存在
1. 缓存空值并设置短TTL；2. 布隆过滤
器前置拦截；3. 参数合法性校验
缓存
击穿
某个热点Key突然过期，大量
并发请求同时查库
热点数据缓存过期瞬
间，高并发访问
1. 互斥锁只允许一个请求查库；2. 热点
数据永不过期；3. 后台异步更新
缓存
雪崩
大量Key同时过期，或Redis
宕机，数据库压力骤增
过期时间相同、Redis
单点故障
1. 过期时间加随机偏移；2. Redis集群
高可用；3. 服务熔断降级
以缓存击穿为例，使用互斥锁解决的核心代码逻辑如下：
SpringBoot企业级后端开发技术手册 V1.0
第 19 页 / 共 30 页

[3] Redis中文文档-最佳实践.html — *2. 缓存击穿防护
*2. 缓存击穿防护

使用互斥锁或热点数据永不过期：

# 互斥锁
if not redis.setnx(f"lock:{key}", "1", ex=10):
    return cache_data
```

**回答**

```
Redis缓存击穿的解决方案包括：  
- 互斥锁：在热点Key过期瞬间，确保只有一个请求访问数据库，其他请求直接返回缓存数据 [1][2][3]  
- 热点数据永不过期：对热点数据设置缓存永不过期，避免过期瞬间的高并发访问 [1][2][3]  
- 逻辑过期：通过逻辑过期机制避免直接访问数据库 [1]  
- 后台异步更新：在热点数据过期时，后台异步更新缓存以减轻数据库压力 [2]

参考来源：
[1] redis.md — Redis 缓存击穿
[2] SpringBoot企业级后端开发技术手册.pdf — 第19页
[3] Redis中文文档-最佳实践.html — *2. 缓存击穿防护
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [3] Redis有哪些常见数据类型

- 金标来源：redis.md
- 金标章节：Redis 数据类型

**上下文片段**

```
[1] redis.md — Redis 数据类型
Redis 数据类型

Redis 常见的数据类型包括：

1. String
2. Hash
3. List
4. Set
5. Sorted Set

其中 String 是最常用的数据类型，可以用于缓存对象、计数器、分布式锁等场景。

[2] Redis中文文档-数据类型.html — *Redis 数据类型与抽象入门
*Redis 数据类型与抽象入门

Redis 不仅仅是一个简单的键值存储，它实际上是一个数据结构服务器，支持多种类型的值。这意味着，在传统的键值存储中，你只能将字符串键关联到字符串值，而在 Redis 中，值不局限于简单的字符串，还可以持有更复杂的数据结构。

以下是 Redis 支持的主要数据结构列表，本教程将逐一介绍：

二进制安全字符串 (Strings)

列表 (Lists)：按插入顺序排序的字符串元素集合，其底层实现是链表。

集合 (Sets)：唯一且无序的字符串元素集合。

有序集合 (Sorted Sets)：类似于集合，但每个字符串元素都关联一个称为分数 (Score) 的浮点数。元素始终按分数排序，因此可以获取指定范围内的元素（例如：获取前 10 名或后 10 名）。

哈希 (Hashes)：由字段 (Field) 与值 (Value) 组成的映射表，字段和值均为字符串。这与 Ruby 或 Python 的 Hash/Dict 非常相似。

位图 (Bitmaps)：利用特殊命令将字符串值当作位数组处理：你可以设置/清除单个比特位、统计设为 1 的位数、查找第一个设置或未设置的位等。

HyperLogLogs：一种概率数据结构，用于估算集合的基数（去重计数）。它比听起来简单得多，请参阅后文相关章节。

流 (Streams)：一种仅追加 (Append-only) 的类映射条目集合，提供抽象的日志数据类型。

仅通过命令参考来理解这些类型的工作原理及其适用场景并不直观，因此本文档旨在作为 Redis 数据类型及其常见模式的速成课程。

示例中我们将使用 redis-cli 工具，这是一个简单方便的命令行界面，用于向 Redis 服务器发出指令。

[3] Redis中文文档-集群规范.html — *为什么避免合并操作
*为什么避免合并操作

Redis 集群设计避免了在多个节点中出现同一键值对的冲突版本，因为在 Redis 数据模型的情况下，这并不总是可取的。Redis 中的值通常非常大；常见的是包含数百万个元素的列表或有序集合。此外，数据类型在语义上很复杂。传输和合并这类值可能成为主要瓶颈，并且/或可能需要应用程序端逻辑的非平凡参与、存储元数据的额外内存等等。

这里没有严格的技术限制。CRDT 或同步复制的状态机可以对类似 Redis 的复杂数据类型建模。然而，这种系统的实际运行时行为不会与 Redis 集群相似。Redis 集群的设计目的是覆盖非集群 Redis 版本的精确用例。
```

**回答**

```
Redis的常见数据类型包括：String、Hash、List、Set、Sorted Set。[1]

参考来源：
[1] redis.md — Redis 数据类型
[2] Redis中文文档-数据类型.html — *Redis 数据类型与抽象入门
[3] Redis中文文档-集群规范.html — *为什么避免合并操作
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [4] MySQL索引是什么

- 金标来源：mysql.md
- 金标章节：MySQL 索引

**上下文片段**

```
[1] MySQL中文教程-索引.html — MySQL 索引
MySQL 索引

MySQL 索引是一种数据结构，用于加快数据库查询的速度和性能。

MySQL 索引的建立对于 MySQL 的高效运行是很重要的，索引可以大大提高 MySQL 的检索速度。

MySQL 索引类似于书籍的索引，通过存储指向数据行的指针，可以快速定位和访问表中的特定数据。

打个比方，如果合理的设计且使用索引的 MySQL 是一辆兰博基尼的话，那么没有设计和使用索引的 MySQL 就是一个人力三轮车。

拿汉语字典的目录页（索引）打比方，我们可以按拼音、笔画、偏旁部首等排序的目录（索引）快速查找到需要的字。

索引分单列索引和组合索引：

单列索引，即一个索引只包含单个列，一个表可以有多个单列索引。

组合索引，即一个索引包含多个列。

创建索引时，你需要确保该索引是应用在 SQL 查询语句的条件(一般作为 WHERE 子句的条件)。

实际上，索引也是一张表，该表保存了主键与索引字段，并指向实体表的记录。

索引虽然能够提高查询性能，但也需要注意以下几点：

索引需要占用额外的存储空间。

对表进行插入、更新和删除操作时，索引需要维护，可能会影响性能。

过多或不合理的索引可能会导致性能下降，因此需要谨慎选择和规划索引。

[2] mysql.md — MySQL 索引
MySQL 索引

索引是一种用于提高数据库查询效率的数据结构。

常见索引类型包括：

- B+Tree 索引
- Hash 索引
- 联合索引
- 唯一索引

InnoDB 默认使用 B+Tree 索引。

[3] mysql.md — MySQL 是什么
MySQL 是什么

MySQL 是一种开源的关系型数据库管理系统，使用 SQL 语言进行数据管理。

MySQL 广泛应用于 Web 应用和企业级后端系统。
```

**回答**

```
MySQL索引是一种数据结构，用于加快数据库查询的速度和性能，可以大大提高MySQL的检索速度。[1]

参考来源：
[1] MySQL中文教程-索引.html — MySQL 索引
[2] mysql.md — MySQL 索引
[3] mysql.md — MySQL 是什么
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [5] MySQL索引有什么作用

- 金标来源：mysql.md
- 金标章节：MySQL 索引

**上下文片段**

```
[1] MySQL中文教程-索引.html — MySQL 索引
MySQL 索引

MySQL 索引是一种数据结构，用于加快数据库查询的速度和性能。

MySQL 索引的建立对于 MySQL 的高效运行是很重要的，索引可以大大提高 MySQL 的检索速度。

MySQL 索引类似于书籍的索引，通过存储指向数据行的指针，可以快速定位和访问表中的特定数据。

打个比方，如果合理的设计且使用索引的 MySQL 是一辆兰博基尼的话，那么没有设计和使用索引的 MySQL 就是一个人力三轮车。

拿汉语字典的目录页（索引）打比方，我们可以按拼音、笔画、偏旁部首等排序的目录（索引）快速查找到需要的字。

索引分单列索引和组合索引：

单列索引，即一个索引只包含单个列，一个表可以有多个单列索引。

组合索引，即一个索引包含多个列。

创建索引时，你需要确保该索引是应用在 SQL 查询语句的条件(一般作为 WHERE 子句的条件)。

实际上，索引也是一张表，该表保存了主键与索引字段，并指向实体表的记录。

索引虽然能够提高查询性能，但也需要注意以下几点：

索引需要占用额外的存储空间。

对表进行插入、更新和删除操作时，索引需要维护，可能会影响性能。

过多或不合理的索引可能会导致性能下降，因此需要谨慎选择和规划索引。

[2] mysql.md — MySQL 索引
MySQL 索引

索引是一种用于提高数据库查询效率的数据结构。

常见索引类型包括：

- B+Tree 索引
- Hash 索引
- 联合索引
- 唯一索引

InnoDB 默认使用 B+Tree 索引。

[3] MySQL中文教程-索引.html — 唯一索引
唯一索引

在 MySQL 中，你可以使用 CREATE UNIQUE INDEX 语句来创建唯一索引。

唯一索引确保索引中的值是唯一的，不允许有重复值。
```

**回答**

```
MySQL索引的作用是加快数据库查询速度，提高检索效率。[1][2]

参考来源：
[1] MySQL中文教程-索引.html — MySQL 索引
[2] mysql.md — MySQL 索引
[3] MySQL中文教程-索引.html — 唯一索引
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [6] Java虚拟机的垃圾回收器有哪些

- 金标来源：java.md
- 金标章节：垃圾回收器

**上下文片段**

```
[1] java.md — 垃圾回收器
垃圾回收器

Serial 收集器：单线程收集，全程 STW，适合客户端场景。
Parallel 收集器：多线程垃圾收集器，以吞吐量为主要目标，在 JDK 8 中是 Server 模式下的默认收集器组合。
CMS 收集器：并发低停顿，标记‑清除算法，存在内存碎片问题。
G1 收集器：基于分代收集的垃圾回收器，支持可预测停顿，JDK 9 中是默认的垃圾回收器。
ZGC 收集器：极低停顿时间，适合大堆内存场景。

[2] java.md — JVM
JVM

JVM 是 Java Virtual Machine 的缩写。

JVM 负责执行 Java 字节码，并提供内存管理和垃圾回收等功能。

[3] java.md — 垃圾回收
垃圾回收

垃圾回收主要针对堆内存中不再使用的对象。
判断对象存活主流算法：可达性分析算法。
GC Roots 作为起点向下遍历，不可到达的对象判定为垃圾对象。
GC Roots 包含栈引用、静态变量引用、本地方法引用等。
Java 分为强、软、弱、虚四种对象引用类型。
```

**回答**

```
Java虚拟机的垃圾回收器有Serial收集器、Parallel收集器、CMS收集器、G1收集器和ZGC收集器。[1]

参考来源：
[1] java.md — 垃圾回收器
[2] java.md — JVM
[3] java.md — 垃圾回收
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [7] Spring IoC是什么

- 金标来源：spring.md
- 金标章节：IoC

**上下文片段**

```
[1] spring.md — IoC
IoC

IoC 即控制反转。

Spring IoC 容器负责创建和管理对象，而不是由业务代码直接创建对象。

[2] Spring框架官方文档-IoC容器.html — The IoC Container
The IoC Container

This chapter covers Spring’s Inversion of Control (IoC) container.

[3] spring.md — Spring 是什么
Spring 是什么

Spring 是 Java 企业级应用开发中常用的开发框架。

Spring 的核心功能包括 IoC 和 AOP。
```

**回答**

```
Spring IoC 即控制反转，Spring IoC 容器负责创建和管理对象，而不是由业务代码直接创建对象。[1]

参考来源：
[1] spring.md — IoC
[2] Spring框架官方文档-IoC容器.html — The IoC Container
[3] spring.md — Spring 是什么
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [8] Spring Bean的生命周期是什么

- 金标来源：spring.md
- 金标章节：Bean 生命周期

**上下文片段**

```
[1] spring.md — Bean 生命周期
Bean 生命周期

Bean 生命周期指 Spring IoC 容器中 Bean 从实例化到销毁的完整过程。主要包含实例化、依赖注入、初始化、就绪使用、销毁几个阶段；可以通过构造方法、setter、InitializingBean、@PostConstruct、DisposableBean、@PreDestroy 等介入生命周期。

[2] Spring框架官方文档-Bean作用域.html — The Prototype Scope
The Prototype Scope

The non-singleton prototype scope of bean deployment results in the creation of a new bean instance every time a request for that specific bean is made. That is, the bean is injected into another bean or you request it through a getBean() method call on the container. As a rule, you should use the prototype scope for all stateful beans and the singleton scope for stateless beans.

The following diagram illustrates the Spring prototype scope:

(A data access object (DAO) is not typically configured as a prototype, because a typical DAO does not hold any conversational state. It was easier for us to reuse the core of the singleton diagram.)

The following example defines a bean as a prototype in XML:

<bean id="accountService" class="com.something.DefaultAccountService" scope="prototype"/>

In contrast to the other scopes, Spring does not manage the complete lifecycle of a prototype bean. The container instantiates, configures, and otherwise assembles a prototype object and hands it to the client, with no further record of that prototype instance. Thus, although initialization lifecycle callback methods are called on all objects regardless of scope, in the case of prototypes, configured destruction lifecycle callbacks are not called. The client code must clean up prototype-scoped objects and release expensive resources that the prototype beans hold. To get the Spring container to release resources held by prototype-scoped beans, try using a custom bean post-processor which holds a reference to beans that need to be cleaned up.

In some respects, the Spring container’s role in regard to a prototype-scoped bean is a replacement for the Java new operator. All lifecycle management past that point must be handled by the client. (For details on the lifecycle of a bean in the Spring container, see Lifecycle Callbacks.)

[3] Spring框架官方文档-IoC容器-Bean Scopes.html — The Prototype Scope
The Prototype Scope

The non-singleton prototype scope of bean deployment results in the creation of a new bean instance every time a request for that specific bean is made. That is, the bean is injected into another bean or you request it through a getBean() method call on the container. As a rule, you should use the prototype scope for all stateful beans and the singleton scope for stateless beans.

The following diagram illustrates the Spring prototype scope:

(A data access object (DAO) is not typically configured as a prototype, because a typical DAO does not hold any conversational state. It was easier for us to reuse the core of the singleton diagram.)

The following example defines a bean as a prototype in XML:

<bean id="accountService" class="com.something.DefaultAccountService" scope="prototype"/>

In contrast to the other scopes, Spring does not manage the complete lifecycle of a prototype bean. The container instantiates, configures, and otherwise assembles a prototype object and hands it to the client, with no further record of that prototype instance. Thus, although initialization lifecycle callback methods are called on all objects regardless of scope, in the case of prototypes, configured destruction lifecycle callbacks are not called. The client code must clean up prototype-scoped objects and release expensive resources that the prototype beans hold. To get the Spring container to release resources held by prototype-scoped beans, try using a custom bean post-processor which holds a reference to beans that need to be cleaned up.

In some respects, the Spring container’s role in regard to a prototype-scoped bean is a replacement for the Java new operator. All lifecycle management past that point must be handled by the client. (For details on the lifecycle of a bean in the Spring container, see Lifecycle Callbacks.)
```

**回答**

```
Spring Bean的生命周期是指Spring IoC容器中Bean从实例化到销毁的完整过程，主要包含实例化、依赖注入、初始化、就绪使用、销毁几个阶段。可以通过构造方法、setter、InitializingBean、@PostConstruct、DisposableBean、@PreDestroy等介入生命周期。[1]

参考来源：
[1] spring.md — Bean 生命周期
[2] Spring框架官方文档-Bean作用域.html — The Prototype Scope
[3] Spring框架官方文档-IoC容器-Bean Scopes.html — The Prototype Scope
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [9] RabbitMQ消息可靠性怎么保证

- 金标来源：rabbitmq.md
- 金标章节：消息可靠性

**上下文片段**

```
[1] SpringBoot官方文档-RabbitMQ集成.html — RabbitMQ Support
RabbitMQ Support

RabbitMQ is a lightweight, reliable, scalable, and portable message broker based on the AMQP protocol. Spring uses RabbitMQ to communicate through the AMQP protocol.

RabbitMQ configuration is controlled by external configuration properties in spring.rabbitmq.*. For example, you might declare the following section in application.properties:

Properties

YAML

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=admin
spring.rabbitmq.password=secret

spring:
  rabbitmq:
    host: "localhost"
    port: 5672
    username: "admin"
    password: "secret"

Alternatively, you could configure the same connection using the addresses attribute:

Properties

YAML

spring.rabbitmq.addresses=amqp://admin:secret@localhost

spring:
  rabbitmq:
    addresses: "amqp://admin:secret@localhost"

| When specifying addresses that way, the host and port properties are ignored. If the address uses the amqps protocol, SSL support is enabled automatically. |

See RabbitProperties for more of the supported property-based configuration options. To configure lower-level details of the RabbitMQ ConnectionFactory that is used by Spring AMQP, define a ConnectionFactoryCustomizer bean.

If a ConnectionNameStrategy bean exists in the context, it will be automatically used to name connections created by the auto-configured CachingConnectionFactory.

To make an application-wide, additive customization to the RabbitTemplate, use a RabbitTemplateCustomizer bean.

| See Understanding AMQP, the protocol used by RabbitMQ for more details. |

[2] rabbitmq.md — 消息可靠性
消息可靠性

为了提高消息可靠性，可以从生产端、Broker 和消费端进行保障。

例如：

- Publisher Confirm
- 消息持久化
- Consumer Ack
- 重试机制

[3] 消息队列选型对比.html — RabbitMQ
RabbitMQ

基于 AMQP 协议，交换机和绑定规则提供灵活的路由能力，消息确认和死信机制完善

吞吐在万级到十万级，延迟低，适合业务消息和任务分发，百万级以上吞吐不是它的强项
```

**回答**

```
RabbitMQ消息可靠性可以通过生产端的Publisher Confirm、消息持久化、消费端的Consumer Ack以及重试机制来保证 [2]。

参考来源：
[1] SpringBoot官方文档-RabbitMQ集成.html — RabbitMQ Support
[2] rabbitmq.md — 消息可靠性
[3] 消息队列选型对比.html — RabbitMQ
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [10] RabbitMQ有哪些核心组件

- 金标来源：rabbitmq.md
- 金标章节：RabbitMQ 核心组件

**上下文片段**

```
[1] rabbitmq.md — RabbitMQ 核心组件
RabbitMQ 核心组件

RabbitMQ 的核心组件包括：

- Producer
- Consumer
- Exchange
- Queue
- Binding

Producer 负责发送消息。

Consumer 负责消费消息。

Exchange 根据路由规则将消息发送到对应的 Queue。

[2] rabbitmq.md — RabbitMQ 是什么
RabbitMQ 是什么

RabbitMQ 是一种开源消息代理和消息队列系统。

它可以用于实现异步通信、应用解耦和流量削峰。

[3] SpringBoot官方文档-RabbitMQ集成.html — RabbitMQ Support
RabbitMQ Support

RabbitMQ is a lightweight, reliable, scalable, and portable message broker based on the AMQP protocol. Spring uses RabbitMQ to communicate through the AMQP protocol.

RabbitMQ configuration is controlled by external configuration properties in spring.rabbitmq.*. For example, you might declare the following section in application.properties:

Properties

YAML

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=admin
spring.rabbitmq.password=secret

spring:
  rabbitmq:
    host: "localhost"
    port: 5672
    username: "admin"
    password: "secret"

Alternatively, you could configure the same connection using the addresses attribute:

Properties

YAML

spring.rabbitmq.addresses=amqp://admin:secret@localhost

spring:
  rabbitmq:
    addresses: "amqp://admin:secret@localhost"

| When specifying addresses that way, the host and port properties are ignored. If the address uses the amqps protocol, SSL support is enabled automatically. |

See RabbitProperties for more of the supported property-based configuration options. To configure lower-level details of the RabbitMQ ConnectionFactory that is used by Spring AMQP, define a ConnectionFactoryCustomizer bean.

If a ConnectionNameStrategy bean exists in the context, it will be automatically used to name connections created by the auto-configured CachingConnectionFactory.

To make an application-wide, additive customization to the RabbitTemplate, use a RabbitTemplateCustomizer bean.

| See Understanding AMQP, the protocol used by RabbitMQ for more details. |
```

**回答**

```
RabbitMQ的核心组件包括Producer、Consumer、Exchange、Queue和Binding[1]。

参考来源：
[1] rabbitmq.md — RabbitMQ 核心组件
[2] rabbitmq.md — RabbitMQ 是什么
[3] SpringBoot官方文档-RabbitMQ集成.html — RabbitMQ Support
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [11] Docker容器是什么

- 金标来源：docker.md
- 金标章节：Docker 容器

**上下文片段**

```
[1] docker.md — Docker 容器
Docker 容器

Container 是镜像运行后的实例。

容器具有隔离性，可以独立运行应用程序。

[2] docker.md — Docker 是什么
Docker 是什么

Docker 是一种容器化技术，可以将应用程序及其运行环境封装到容器中。

[3] docker.md — Docker 镜像
Docker 镜像

Docker Image 是用于创建容器的只读模板。

镜像中包含应用程序运行所需要的文件和环境。
```

**回答**

```
Docker容器是镜像运行后的实例，具有隔离性，可以独立运行应用程序。[1]

参考来源：
[1] docker.md — Docker 容器
[2] docker.md — Docker 是什么
[3] docker.md — Docker 镜像
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [12] Docker Compose有什么作用

- 金标来源：docker.md
- 金标章节：Docker Compose

**上下文片段**

```
[1] docker.md — Docker Compose
Docker Compose

Docker Compose 用于定义和运行多个容器组成的应用。

例如一个 Web 系统可以通过 Docker Compose 同时运行：

- MySQL
- Redis
- RabbitMQ
- Web Application

[2] docker.md — Docker 网络
Docker 网络

Docker 默认提供 bridge、host、none 三种网络模式。

bridge 模式通过虚拟网桥让容器之间互相通信，并通过端口映射对外暴露服务。

同一自定义网络中的容器可以使用容器名互相访问，Compose 编排的服务默认加入同一个网络，因此服务之间可以直接用服务名作为主机名访问。

[3] docker.md — Docker 是什么
Docker 是什么

Docker 是一种容器化技术，可以将应用程序及其运行环境封装到容器中。
```

**回答**

```
Docker Compose用于定义和运行多个容器组成的应用。[1]

参考来源：
[1] docker.md — Docker Compose
[2] docker.md — Docker 网络
[3] docker.md — Docker 是什么
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [13] 多个服务实例如何控制对共享资源的并发访问？

- 金标来源：redis.md
- 金标章节：Redis 分布式锁

**上下文片段**

```
[1] redis.md — Redis 分布式锁
Redis 分布式锁

Redis 可以利用 SET 命令实现分布式锁。

分布式锁可以用于控制多个服务实例对共享资源的并发访问。

实现分布式锁时需要考虑锁的原子性、过期时间以及误删锁等问题。

[2] operating-systems.md — IO 多路复用
IO 多路复用

IO 多路复用让单个线程同时监听多个文件描述符的就绪事件。

三种实现：select 用固定大小的位图，每次调用都要全量拷贝和遍历；poll 改用链表突破数量限制；epoll 通过红黑树注册描述符、就绪链表返回事件，支持海量并发连接。

Redis、Nginx 等高性能服务都基于 epoll 实现事件驱动模型。

[3] operating-systems.md — 进程与线程
进程与线程

进程是资源分配的基本单位，拥有独立的内存空间；线程是 CPU 调度的基本单位，同一进程内的线程共享进程的内存和资源。

进程切换开销大，需要切换页表和刷新缓存；线程切换开销小，但共享内存带来并发安全问题。

协程是用户态的轻量级执行单元，切换完全在用户空间完成，开销比线程更小，适合高并发 IO 场景。
```

**回答**

```
多个服务实例可以通过分布式锁（例如Redis基于SET命令实现）来控制对共享资源的并发访问。[1]

参考来源：
[1] redis.md — Redis 分布式锁
[2] operating-systems.md — IO 多路复用
[3] operating-systems.md — 进程与线程
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [14] Redis中怎样实现分布式锁？

- 金标来源：redis.md
- 金标章节：Redis 分布式锁

**上下文片段**

```
[1] Redis中文文档-分布式锁.html — *为什么基于故障转移的实现还不够
*为什么基于故障转移的实现还不够

为了更好的理解我们想要改进的方面，我们先分析一下当前大多数基于Redis的分布式锁现状和实现方法.

实现Redis分布式锁的最简单的方法就是在Redis中创建一个key，这个key有一个失效时间（TTL)，以保证锁最终会被自动释放掉（这个对应特性2）。当客户端释放资源(解锁）的时候，会删除掉这个key。

从表面上看，似乎效果还不错，但是这里有一个问题：这个架构中存在一个严重的单点失败问题。如果Redis挂了怎么办？你可能会说，可以通过增加一个slave节点解决这个问题。但这通常是行不通的。这样做，我们不能实现资源的独享,因为Redis的主从同步通常是异步的。

在这种场景（主从结构）中存在明显的竞态:

客户端A从master获取到锁

在master将锁同步到slave之前，master宕掉了。

slave节点被晋级为master节点

客户端B取得了同一个资源被客户端A已经获取到的另外一个锁。安全失效！

有时候程序就是这么巧，比如说正好一个节点挂掉的时候，多个客户端同时取到了锁。如果你可以接受这种小概率错误，那用这个基于复制的方案就完全没有问题。否则的话，我们建议你实现下面描述的解决方案。

[2] redis.md — Redis 分布式锁
Redis 分布式锁

Redis 可以利用 SET 命令实现分布式锁。

分布式锁可以用于控制多个服务实例对共享资源的并发访问。

实现分布式锁时需要考虑锁的原子性、过期时间以及误删锁等问题。

[3] Redis中文文档-分布式锁.html — *单Redis实例实现分布式锁的正确方法
*单Redis实例实现分布式锁的正确方法

在尝试克服上述单实例设置的限制之前，让我们先讨论一下在这种简单情况下实现分布式锁的正确做法，实际上这是一种可行的方案，尽管存在竞态，结果仍然是可接受的，另外，这里讨论的单实例加锁方法也是分布式加锁算法的基础。

获取锁使用命令:

SET resource_name my_random_value NX PX 30000

这个命令仅在不存在key的时候才能被执行成功（NX选项），并且这个key有一个30秒的自动失效时间（PX属性）。这个key的值是"myrandomvalue"(一个随机值），这个值在所有的客户端必须是唯一的，所有同一key的获取者（竞争者）这个值都不能一样。

value的值必须是随机数主要是为了更安全的释放锁，释放锁的时候使用脚本告诉Redis:只有key存在并且存储的值和我指定的值一样才能告诉我删除成功。可以通过以下Lua脚本实现：

if redis.call("get",KEYS[1]) == ARGV[1] then
    return redis.call("del",KEYS[1])
else
    return 0
end

使用这种方式释放锁可以避免删除别的客户端获取成功的锁。举个例子：客户端A取得资源锁，但是紧接着被一个其他操作阻塞了，当客户端A运行完毕其他操作后要释放锁时，原来的锁早已超时并且被Redis自动释放，并且在这期间资源锁又被客户端B再次获取到。如果仅使用DEL命令将key删除，那么这种情况就会把客户端B的锁给删除掉。使用Lua脚本就不会存在这种情况，因为脚本仅会删除value等于客户端A的value的key（value相当于客户端的一个签名）。

这个随机字符串应该怎么设置？我认为它应该是从/dev/urandom产生的一个20字节随机数，但是我想你可以找到比这种方法代价更小的方法，只要这个数在你的任务中是唯一的就行。例如一种安全可行的方法是使用/dev/urandom作为RC4的种子和源产生一个伪随机流;一种更简单的方法是把以毫秒为单位的unix时间和客户端ID拼接起来，理论上不是完全安全，但是在多数情况下可以满足需求.
```

**回答**

```
Redis可以利用SET命令实现分布式锁 [2]。获取锁命令为 `SET resource_name my_random_value NX PX 30000` [3]，其中my_random_value需为唯一随机值，NX确保锁仅在key不存在时设置，PX设置锁的过期时间；释放锁时使用Lua脚本 `if redis.call("get",KEYS[1]) == ARGV[1] then return redis.call("del",KEYS[1]) else return 0 end` [3] 以避免误删锁。

参考来源：
[1] Redis中文文档-分布式锁.html — *为什么基于故障转移的实现还不够
[2] redis.md — Redis 分布式锁
[3] Redis中文文档-分布式锁.html — *单Redis实例实现分布式锁的正确方法
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [15] Redis缓存击穿时应该采取什么措施？

- 金标来源：redis.md
- 金标章节：Redis 缓存击穿

**上下文片段**

```
[1] redis.md — Redis 缓存击穿
Redis 缓存击穿

缓存击穿通常发生在某个热点 Key 过期的瞬间，大量并发请求同时访问数据库。

常见解决方案包括：

- 互斥锁
- 逻辑过期
- 热点数据永不过期

[2] Redis中文文档-最佳实践.html — *2. 缓存击穿防护
*2. 缓存击穿防护

使用互斥锁或热点数据永不过期：

# 互斥锁
if not redis.setnx(f"lock:{key}", "1", ex=10):
    return cache_data

[3] SpringBoot企业级后端开发技术手册.pdf — 第19页
图3 Redis缓存穿透/击穿/雪崩问题处理架构图
三类问题的定义、产生原因与解决方案如下表所示：
问题
类型
问题定义 产生原因 解决方案
缓存
穿透
查询数据库中不存在的数
据，缓存永远无法命中
恶意攻击、非法参数、
业务数据不存在
1. 缓存空值并设置短TTL；2. 布隆过滤
器前置拦截；3. 参数合法性校验
缓存
击穿
某个热点Key突然过期，大量
并发请求同时查库
热点数据缓存过期瞬
间，高并发访问
1. 互斥锁只允许一个请求查库；2. 热点
数据永不过期；3. 后台异步更新
缓存
雪崩
大量Key同时过期，或Redis
宕机，数据库压力骤增
过期时间相同、Redis
单点故障
1. 过期时间加随机偏移；2. Redis集群
高可用；3. 服务熔断降级
以缓存击穿为例，使用互斥锁解决的核心代码逻辑如下：
SpringBoot企业级后端开发技术手册 V1.0
第 19 页 / 共 30 页
```

**回答**

```
缓存击穿时，应使用互斥锁[1][2][3]、热点数据永不过期[1][2][3]和后台异步更新[3]进行防护。

参考来源：
[1] redis.md — Redis 缓存击穿
[2] Redis中文文档-最佳实践.html — *2. 缓存击穿防护
[3] SpringBoot企业级后端开发技术手册.pdf — 第19页
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [16] Redis支持哪些常用的数据结构？

- 金标来源：redis.md
- 金标章节：Redis 数据类型

**上下文片段**

```
[1] Redis中文文档-数据类型.html — *Redis 数据类型与抽象入门
*Redis 数据类型与抽象入门

Redis 不仅仅是一个简单的键值存储，它实际上是一个数据结构服务器，支持多种类型的值。这意味着，在传统的键值存储中，你只能将字符串键关联到字符串值，而在 Redis 中，值不局限于简单的字符串，还可以持有更复杂的数据结构。

以下是 Redis 支持的主要数据结构列表，本教程将逐一介绍：

二进制安全字符串 (Strings)

列表 (Lists)：按插入顺序排序的字符串元素集合，其底层实现是链表。

集合 (Sets)：唯一且无序的字符串元素集合。

有序集合 (Sorted Sets)：类似于集合，但每个字符串元素都关联一个称为分数 (Score) 的浮点数。元素始终按分数排序，因此可以获取指定范围内的元素（例如：获取前 10 名或后 10 名）。

哈希 (Hashes)：由字段 (Field) 与值 (Value) 组成的映射表，字段和值均为字符串。这与 Ruby 或 Python 的 Hash/Dict 非常相似。

位图 (Bitmaps)：利用特殊命令将字符串值当作位数组处理：你可以设置/清除单个比特位、统计设为 1 的位数、查找第一个设置或未设置的位等。

HyperLogLogs：一种概率数据结构，用于估算集合的基数（去重计数）。它比听起来简单得多，请参阅后文相关章节。

流 (Streams)：一种仅追加 (Append-only) 的类映射条目集合，提供抽象的日志数据类型。

仅通过命令参考来理解这些类型的工作原理及其适用场景并不直观，因此本文档旨在作为 Redis 数据类型及其常见模式的速成课程。

示例中我们将使用 redis-cli 工具，这是一个简单方便的命令行界面，用于向 Redis 服务器发出指令。

[2] redis.md — Redis 数据类型
Redis 数据类型

Redis 常见的数据类型包括：

1. String
2. Hash
3. List
4. Set
5. Sorted Set

其中 String 是最常用的数据类型，可以用于缓存对象、计数器、分布式锁等场景。

[3] redis.md — Redis 是什么
Redis 是什么

Redis 是一个开源的内存数据结构存储系统，可以作为数据库、缓存和消息中间件使用。

Redis 的主要特点是基于内存进行数据读写，因此具有较低的访问延迟和较高的吞吐能力。
```

**回答**

```
Redis支持的常用数据结构包括字符串（String）、哈希（Hash）、列表（List）、集合（Set）和有序集合（Sorted Set）[2]。

参考来源：
[1] Redis中文文档-数据类型.html — *Redis 数据类型与抽象入门
[2] redis.md — Redis 数据类型
[3] redis.md — Redis 是什么
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [17] 为什么MySQL需要建立索引？

- 金标来源：mysql.md
- 金标章节：MySQL 索引

**上下文片段**

```
[1] MySQL中文教程-索引.html — MySQL 索引
MySQL 索引

MySQL 索引是一种数据结构，用于加快数据库查询的速度和性能。

MySQL 索引的建立对于 MySQL 的高效运行是很重要的，索引可以大大提高 MySQL 的检索速度。

MySQL 索引类似于书籍的索引，通过存储指向数据行的指针，可以快速定位和访问表中的特定数据。

打个比方，如果合理的设计且使用索引的 MySQL 是一辆兰博基尼的话，那么没有设计和使用索引的 MySQL 就是一个人力三轮车。

拿汉语字典的目录页（索引）打比方，我们可以按拼音、笔画、偏旁部首等排序的目录（索引）快速查找到需要的字。

索引分单列索引和组合索引：

单列索引，即一个索引只包含单个列，一个表可以有多个单列索引。

组合索引，即一个索引包含多个列。

创建索引时，你需要确保该索引是应用在 SQL 查询语句的条件(一般作为 WHERE 子句的条件)。

实际上，索引也是一张表，该表保存了主键与索引字段，并指向实体表的记录。

索引虽然能够提高查询性能，但也需要注意以下几点：

索引需要占用额外的存储空间。

对表进行插入、更新和删除操作时，索引需要维护，可能会影响性能。

过多或不合理的索引可能会导致性能下降，因此需要谨慎选择和规划索引。

[2] MySQL中文教程-索引.html — 普通索引
普通索引

索引能够显著提高查询的速度，尤其是在大型表中进行搜索时。通过使用索引，MySQL 可以直接定位到满足查询条件的数据行，而无需逐行扫描整个表。

[3] SpringBoot企业级后端开发技术手册.pdf — 第16页
问题场景 优化方案 原理说明
查询条件未命中索引
建立联合索引，遵循最左前缀原
则
联合索引按字段顺序构建B+树，必须从最左
字段开始匹配
LIKE '%xxx'前缀模糊
查询
改用ElasticSearch全文检索引擎
前缀模糊查询无法利用B+树索引，会导致全
表扫描
对索引列使用函数/运
算
将运算移到条件右侧，或建立函
数索引
对索引列使用函数会导致索引失效
隐式类型转换
保证查询参数类型与字段类型一
致
字符串字段用数字查询会触发隐式转换，导致
索引失效
大量更新的字段
不要在频繁更新的字段上建立索
引
每次更新都会同时维护索引，严重影响写入性
能
低区分度字段
避免在性别、状态等字段单独建
索引
区分度低的字段过滤效果差，优化器可能选择
全表扫描
ORDER BY/GROUP BY
字段
为排序和分组字段建立索引
索引本身有序，可以避免额外的filesort排序
操作
5.3 慢查询排查与优化
当系统出现接口响应慢的问题时，首先应排查是否存在慢SQL。MySQL慢查询排查流程如下：
开启慢查询日志：设置 slow_query_log=ON ， long_query_time=0.2 （超过200ms的SQL会被
记录）；
分析慢查询日志：使用 mysqldumpslow 工具汇总分析，找出执行次数最多、耗时最长的SQL；
查看执行计划：对慢SQL使用 EXPLAIN 命令查看执行计划，重点关注type、key、rows、Extra四
个字段；
针对性优化：根据执行计划结果，通过添加索引、改写SQL、调整表结构等方式进行优化；
验证优化效果：优化后再次执行SQL，查看执行时间与执行计划，确认优化生效。
EXPLAIN执行计划中常见的type类型性能从好到差依次为：system > const > eq_ref > ref > range >
index > ALL。如果出现type为ALL，说明是全表扫描，必须进行优化。
1. 
2. 
3. 
4. 
5. 
SpringBoot企业级后端开发技术手册 V1.0
第 16 页 / 共 30 页
```

**回答**

```
MySQL需要建立索引是为了加快数据库查询的速度和性能。[1]  
索引能够显著提高查询的速度，尤其是在大型表中进行搜索时。[2]

参考来源：
[1] MySQL中文教程-索引.html — MySQL 索引
[2] MySQL中文教程-索引.html — 普通索引
[3] SpringBoot企业级后端开发技术手册.pdf — 第16页
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [18] MySQL索引通常使用什么数据结构？

- 金标来源：mysql.md
- 金标章节：MySQL 索引

**上下文片段**

```
[1] mysql.md — MySQL 索引
MySQL 索引

索引是一种用于提高数据库查询效率的数据结构。

常见索引类型包括：

- B+Tree 索引
- Hash 索引
- 联合索引
- 唯一索引

InnoDB 默认使用 B+Tree 索引。

[2] MySQL中文教程-索引.html — MySQL 索引
MySQL 索引

MySQL 索引是一种数据结构，用于加快数据库查询的速度和性能。

MySQL 索引的建立对于 MySQL 的高效运行是很重要的，索引可以大大提高 MySQL 的检索速度。

MySQL 索引类似于书籍的索引，通过存储指向数据行的指针，可以快速定位和访问表中的特定数据。

打个比方，如果合理的设计且使用索引的 MySQL 是一辆兰博基尼的话，那么没有设计和使用索引的 MySQL 就是一个人力三轮车。

拿汉语字典的目录页（索引）打比方，我们可以按拼音、笔画、偏旁部首等排序的目录（索引）快速查找到需要的字。

索引分单列索引和组合索引：

单列索引，即一个索引只包含单个列，一个表可以有多个单列索引。

组合索引，即一个索引包含多个列。

创建索引时，你需要确保该索引是应用在 SQL 查询语句的条件(一般作为 WHERE 子句的条件)。

实际上，索引也是一张表，该表保存了主键与索引字段，并指向实体表的记录。

索引虽然能够提高查询性能，但也需要注意以下几点：

索引需要占用额外的存储空间。

对表进行插入、更新和删除操作时，索引需要维护，可能会影响性能。

过多或不合理的索引可能会导致性能下降，因此需要谨慎选择和规划索引。

[3] MySQL中文教程-索引.html — 普通索引
普通索引

索引能够显著提高查询的速度，尤其是在大型表中进行搜索时。通过使用索引，MySQL 可以直接定位到满足查询条件的数据行，而无需逐行扫描整个表。
```

**回答**

```
MySQL索引通常使用B+Tree数据结构 [1]

参考来源：
[1] mysql.md — MySQL 索引
[2] MySQL中文教程-索引.html — MySQL 索引
[3] MySQL中文教程-索引.html — 普通索引
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [19] JVM中有哪些常见的垃圾收集器？

- 金标来源：java.md
- 金标章节：垃圾回收器

**上下文片段**

```
[1] java.md — 垃圾回收器
垃圾回收器

Serial 收集器：单线程收集，全程 STW，适合客户端场景。
Parallel 收集器：多线程垃圾收集器，以吞吐量为主要目标，在 JDK 8 中是 Server 模式下的默认收集器组合。
CMS 收集器：并发低停顿，标记‑清除算法，存在内存碎片问题。
G1 收集器：基于分代收集的垃圾回收器，支持可预测停顿，JDK 9 中是默认的垃圾回收器。
ZGC 收集器：极低停顿时间，适合大堆内存场景。

[2] java.md — JVM 内存区域
JVM 内存区域

程序计数器：线程私有，记录字节码执行行号，唯一不会发生 OOM 的内存区域。
虚拟机栈：线程私有，存放局部变量、方法返回地址，方法调用对应栈帧入栈出栈。
本地方法栈：线程私有，为 Native 本地方法提供运行空间。
Java 堆：线程共享，存放对象实例，垃圾回收的主要工作区域。
方法区（元空间）：是 JVM 规范定义的逻辑区域，线程共享，用于存储类元数据、运行时常量池等信息。在 HotSpot JDK 8 及以后，方法区的主要实现是元空间（Metaspace），元空间使用本地内存。

[3] java.md — JVM
JVM

JVM 是 Java Virtual Machine 的缩写。

JVM 负责执行 Java 字节码，并提供内存管理和垃圾回收等功能。
```

**回答**

```
JVM中常见的垃圾收集器包括：  
- Serial 收集器：单线程收集，全程 STW，适合客户端场景。[1]  
- Parallel 收集器：多线程垃圾收集器，以吞吐量为主要目标，在 JDK 8 中是 Server 模式下的默认收集器组合。[1]  
- CMS 收集器：并发低停顿，标记‑清除算法，存在内存碎片问题。[1]  
- G1 收集器：基于分代收集的垃圾回收器，支持可预测停顿，JDK 9 中是默认的垃圾回收器。[1]  
- ZGC 收集器：极低停顿时间，适合大堆内存场景。[1]

参考来源：
[1] java.md — 垃圾回收器
[2] java.md — JVM 内存区域
[3] java.md — JVM
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---

### [20] Spring容器中的对象是由谁负责创建和管理的？

- 金标来源：spring.md
- 金标章节：IoC

**上下文片段**

```
[1] spring.md — IoC
IoC

IoC 即控制反转。

Spring IoC 容器负责创建和管理对象，而不是由业务代码直接创建对象。

[2] Spring框架官方文档-IoC容器-Bean Scopes.html — 图片描述
【图片】Spring框架官方文档-IoC容器-Bean Scopes.html

这张图片展示了一个技术文档中的配图，描述了在Spring框架中使用`<bean>`标签创建和管理bean实例的过程。图中包含以下关键组件：

1. 一个`<bean>`标签，id为"..."，class为"..."，属性中包含一个名为"accountDao"的属性，其值为"accountDao"，scope属性为"prototype"。
2. 一个`<bean>`标签，id为"..."，class为"..."，属性中包含一个名为"accountDao"的属性，其值为"accountDao"，scope属性为"prototype"。
3. 一个`<bean>`标签，id为"..."，class为"..."，属性中包含一个名为"accountDao"的属性，其值为"accountDao"，scope属性为"prototype"。

图中还标注了以下内容：
- 第1个`<bean>`标签表示创建了一个新的bean实例。
- 第2个和第3个`<bean>`标签表示每次当协作的bean引用这个bean时，都会创建一个新的bean实例。
- 第3个`<bean>`标签的scope属性为"prototype"，表示这个bean实例是原型实例，每次引用时都会创建一个新的实例。

[3] Spring框架官方文档-IoC容器-Bean Scopes.html — 图片描述
【图片】Spring框架官方文档-IoC容器-Bean Scopes.html

这张图片展示了一个技术文档中的配图，描述了在Spring框架中使用`<bean>`标签创建和管理bean实例的过程。图中包含以下关键组件：

1. 一个`<bean>`标签，id为"..."，class为"..."，属性中包含一个名为"accountDao"的属性，其值为"accountDao"，scope属性为"prototype"。
2. 一个`<bean>`标签，id为"..."，class为"..."，属性中包含一个名为"accountDao"的属性，其值为"accountDao"，scope属性为"prototype"。
3. 一个`<bean>`标签，id为"..."，class为"..."，属性中包含一个名为"accountDao"的属性，其值为"accountDao"，scope属性为"prototype"。

图中还标注了以下内容：
- 第1个`<bean>`标签表示创建了一个新的bean实例。
- 第2个和第3个`<bean>`标签表示每次当协作的bean引用这个bean时，都会创建一个新的bean实例。
- 第3个`<bean>`标签的scope属性为"prototype"，表示这个bean实例是原型实例，每次引用时都会创建一个新的实例。
```

**回答**

```
Spring容器中的对象是由Spring IoC容器负责创建和管理的。[1]

参考来源：
[1] spring.md — IoC
[2] Spring框架官方文档-IoC容器-Bean Scopes.html — 图片描述
[3] Spring框架官方文档-IoC容器-Bean Scopes.html — 图片描述
```

评分：faithfulness = ?　relevancy = ?　correctness = ?

---
