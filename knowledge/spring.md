# Spring 技术知识库

## Spring 是什么

Spring 是 Java 企业级应用开发中常用的开发框架。

Spring 的核心功能包括 IoC 和 AOP。

## IoC

IoC 即控制反转。

Spring IoC 容器负责创建和管理对象，而不是由业务代码直接创建对象。

## DI

DI 即依赖注入。

依赖注入是 IoC 的一种具体实现方式，Spring 可以通过构造器、Setter 或字段等方式注入依赖。

## AOP

AOP 即面向切面编程。

AOP 可以将日志、事务、权限校验等横切关注点从核心业务逻辑中分离出来。

## Spring Boot

Spring Boot 用于简化 Spring 应用的创建和配置。

它通过自动配置和约定优于配置减少开发人员的配置工作。

## Bean 生命周期

Bean 生命周期指 Spring IoC 容器中 Bean 从实例化到销毁的完整过程。主要包含实例化、依赖注入、初始化、就绪使用、销毁几个阶段；可以通过构造方法、setter、InitializingBean、@PostConstruct、DisposableBean、@PreDestroy 等介入生命周期。

## BeanFactory

BeanFactory 是 Spring IoC 容器的顶层根接口，定义了 Bean 的基础获取、查询能力。它采用懒加载，只有调用 getBean () 时才会实例化 Bean，提供最基础的 IoC 容器功能。

## ApplicationContext

ApplicationContext 是 BeanFactory 的子接口，属于高级 IoC 容器。在 BeanFactory 基础上扩展了资源加载、事件发布、国际化、Bean 预实例化等能力；容器启动时就会完成大部分单例 Bean 的创建。

## 三级缓存

三级缓存是 Spring 解决单例 Bean 循环依赖的核心存储结构。

- 一级缓存：singletonObjects，存放完全初始化完成的单例 Bean；
- 二级缓存：earlySingletonObjects，存放实例化完成但未完成属性注入的原始对象；
- 三级缓存：singletonFactories，存放生成 Bean 早期对象的工厂对象。

## 循环依赖

循环依赖指两个或多个 Bean 互相依赖对方作为自身属性。Spring 默认可以解决**单例模式**下的 setter 注入循环依赖；原型 Bean、构造器注入场景无法解决循环依赖。

## AOP 动态代理

AOP 动态代理是 Spring AOP 的底层实现机制，在运行时生成代理对象，不修改原有业务类源码，通过代理对象完成切面逻辑增强。Spring AOP 会根据目标类是否实现接口自动选择代理方式。

## JDK Proxy

JDK 动态代理，JDK 原生提供的代理技术。要求目标对象**必须实现接口**，基于接口生成代理类；代理对象可以拦截接口方法的调用。。

## CGLIB

CGLIB 动态代理，基于字节码生成目标类的子类作为代理对象。不需要目标类实现接口；通过继承重写非 final 方法实现增强，被 final 修饰的类 / 方法无法代理。

## Spring Boot 自动配置

Spring Boot 自动配置基于条件注解、SPI、@EnableAutoConfiguration，扫描 META‑INF/spring/org.springframework.boot.autoconfigure.imports 文件，根据项目 classpath、类是否存在、Bean 是否存在等条件，自动装配对应的 Bean，省去大量手动 XML 或 JavaConfig 配置。

## Spring Boot Starter

Starter 是 Spring Boot 的依赖封装方案。把一组相关依赖版本、自动配置封装在一起；开发只需要引入对应 starter，无需手动管理一堆依赖和版本，快速集成对应功能。例如 spring‑boot‑starter‑web。
## Spring 事务

Spring 通过 AOP 实现声明式事务管理，@Transactional 注解的方法在执行时由事务管理器开启、提交或回滚事务。

默认只在遇到 RuntimeException 和 Error 时回滚，受检异常不回滚，可以通过 rollbackFor 属性调整。

事务失效的常见场景：方法不是 public、自调用、异常被 try-catch 吞掉、数据库引擎不支持事务。

## 事务传播行为

事务传播行为定义一个事务方法被另一个事务方法调用时，事务如何传递。

常用传播行为：REQUIRED 表示当前有事务就加入，没有就新建；REQUIRES_NEW 表示挂起当前事务并新建独立事务；NESTED 表示在当前事务内设置保存点，可以部分回滚。

REQUIRES_NEW 的内层事务提交或回滚不影响外层事务，适合记录操作日志等必须独立提交的场景。
