# Docker 技术知识库

## Docker 是什么

Docker 是一种容器化技术，可以将应用程序及其运行环境封装到容器中。

## Docker 镜像

Docker Image 是用于创建容器的只读模板。

镜像中包含应用程序运行所需要的文件和环境。

## Docker 容器

Container 是镜像运行后的实例。

容器具有隔离性，可以独立运行应用程序。

## Docker Compose

Docker Compose 用于定义和运行多个容器组成的应用。

例如一个 Web 系统可以通过 Docker Compose 同时运行：

- MySQL
- Redis
- RabbitMQ
- Web Application

## Docker 常见命令

docker images 用于查看镜像。

docker ps 用于查看运行中的容器。

docker run 用于创建并启动容器。

docker stop 用于停止容器。
## Docker 数据卷

数据卷是宿主机目录与容器目录之间的映射机制，解决容器删除后数据丢失的问题。

Volume 由 Docker 统一管理，适合持久化业务数据；Bind Mount 直接映射宿主机路径，适合挂载配置文件和开发环境代码。

数据卷的生命周期独立于容器，容器删除后数据卷中的数据仍然保留。

## Docker 网络

Docker 默认提供 bridge、host、none 三种网络模式。

bridge 模式通过虚拟网桥让容器之间互相通信，并通过端口映射对外暴露服务。

同一自定义网络中的容器可以使用容器名互相访问，Compose 编排的服务默认加入同一个网络，因此服务之间可以直接用服务名作为主机名访问。
