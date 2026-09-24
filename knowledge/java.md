# Java 技术知识库

## Java 是什么

Java 是一种面向对象的编程语言，具有跨平台、面向对象和自动内存管理等特点。

## Java 集合

Java 常见集合包括：

- ArrayList
- LinkedList
- HashMap
- HashSet
- ConcurrentHashMap

ArrayList 底层基于动态数组实现。

HashMap 用于存储键值对数据。

## HashMap

HashMap 底层主要由数组、链表和红黑树组成。

当多个 Key 映射到同一个数组位置时，会产生哈希冲突。

HashMap 通过链地址法解决哈希冲突。

当链表长度达到一定条件时，链表可能转换为红黑树，以提高查询效率。

## JVM

JVM 是 Java Virtual Machine 的缩写。

JVM 负责执行 Java 字节码，并提供内存管理和垃圾回收等功能。

## JVM 内存区域

程序计数器：线程私有，记录字节码执行行号，唯一不会发生 OOM 的内存区域。
虚拟机栈：线程私有，存放局部变量、方法返回地址，方法调用对应栈帧入栈出栈。
本地方法栈：线程私有，为 Native 本地方法提供运行空间。
Java 堆：线程共享，存放对象实例，垃圾回收的主要工作区域。
方法区（元空间）：是 JVM 规范定义的逻辑区域，线程共享，用于存储类元数据、运行时常量池等信息。在 HotSpot JDK 8 及以后，方法区的主要实现是元空间（Metaspace），元空间使用本地内存。


## 垃圾回收

垃圾回收主要针对堆内存中不再使用的对象。
判断对象存活主流算法：可达性分析算法。
GC Roots 作为起点向下遍历，不可到达的对象判定为垃圾对象。
GC Roots 包含栈引用、静态变量引用、本地方法引用等。
Java 分为强、软、弱、虚四种对象引用类型。

## 垃圾回收器

Serial 收集器：单线程收集，全程 STW，适合客户端场景。
Parallel 收集器：多线程垃圾收集器，以吞吐量为主要目标，在 JDK 8 中是 Server 模式下的默认收集器组合。
CMS 收集器：并发低停顿，标记‑清除算法，存在内存碎片问题。
G1 收集器：基于分代收集的垃圾回收器，支持可预测停顿，JDK 9 中是默认的垃圾回收器。
ZGC 收集器：极低停顿时间，适合大堆内存场景。

## Java 并发

volatile：保证可见性、禁止指令重排序，不保证原子性。
synchronized：悲观锁，支持修饰方法与代码块，锁对象实现同步。
Lock：显式锁，需要手动加锁解锁，支持公平锁与非公平锁。
CAS：乐观锁机制，基于比较交换实现，存在 ABA 问题。
线程六种状态：

- NEW
- RUNNABLE
- BLOCKED
- WAITING
- TIMED_WAITING
- TERMINATED

线程池：复用线程，核心参数包含核心线程数、最大线程数、阻塞队列、拒绝策略。

## ArrayList

ArrayList 底层基于可变 Object 动态数组实现。
支持随机访问，查询速度快。
在数组中间位置增删元素需要移动大量元素，效率较低。
线程不安全，多线程场景不推荐直接使用。

## LinkedList

LinkedList 底层基于双向链表实现。
不支持随机访问，获取元素需要遍历链表。
首尾位置增删元素效率高，无需移动数据。
可作为普通链表、队列、双端队列使用。
线程不安全。

## HashMap 红黑树

链表转红黑树条件：链表长度≥8，并且数组容量≥64。
如果链表长度达到 8，但数组容量小于 64，则优先触发扩容。
当红黑树节点数量小于等于 6 时，红黑树退化为链表。
红黑树用来解决哈希冲突严重时链表过长导致查询变慢的问题。

## ConcurrentHashMap

JDK1.7 使用 Segment 分段锁实现线程安全。
JDK1.8 取消分段锁，采用 CAS + synchronized 锁链表头节点。
底层结构为数组、链表、红黑树，读操作大多无锁。
key 和 value 都不允许存入 null 值。
并发读写性能优于 Hashtable。
## 线程池

线程池通过复用线程减少创建和销毁的开销，并控制并发数量。

ThreadPoolExecutor 的核心参数：corePoolSize 核心线程数、maximumPoolSize 最大线程数、keepAliveTime 空闲线程存活时间、workQueue 任务队列、拒绝策略。

任务提交顺序：核心线程、任务队列、非核心线程、拒绝策略。

拒绝策略包括：AbortPolicy 抛异常、CallerRunsPolicy 调用者执行、DiscardPolicy 丢弃、DiscardOldestPolicy 丢弃最旧任务。

线程池大小经验值：CPU 密集型约为核数加一，IO 密集型可以设置为核数的两倍左右，最终以压测为准。

## ThreadLocal

ThreadLocal 为每个线程提供独立的变量副本，实现线程隔离。

每个线程内部有一个 ThreadLocalMap，以 ThreadLocal 实例为 Key 存取值。

使用不当会引发内存泄漏：ThreadLocalMap 的 Key 是弱引用，Value 是强引用，线程池中线程长期存活时 Value 无法回收，因此使用完毕必须调用 remove 方法。

ThreadLocal 常用于保存用户上下文、数据库连接、日期格式化对象等线程私有数据。
