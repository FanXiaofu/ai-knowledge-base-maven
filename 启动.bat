@echo off
chcp 936 >nul
title AI 知识库问答系统 - 本地启动
cd /d "%~dp0"

set "APP_JAR=target\ai-knowledge-base-0.0.1-SNAPSHOT.jar"

echo ============================================================
echo   AI 知识库问答系统 - 本地启动
echo ============================================================
echo.

REM ---------- 1. 检查 Docker ----------
echo [1/5] 检查 Docker ...
docker info >nul 2>&1
if errorlevel 1 (
    echo        [失败] Docker 未运行，请先启动 Docker Desktop 后重试
    goto :fail
)
echo        正常

REM ---------- 2. 检查 Java ----------
echo [2/5] 检查 Java ...
java -version >nul 2>&1
if errorlevel 1 (
    echo        [失败] 未找到 Java，请先安装 JDK 17 或更高版本
    goto :fail
)
echo        正常

REM ---------- 3. 检查应用包 ----------
echo [3/5] 检查应用包 ...
if not exist "%APP_JAR%" (
    echo        未找到 %APP_JAR%
    echo        开始构建（首次构建需要几分钟）...
    call mvnw.cmd -DskipTests package
    if errorlevel 1 (
        echo        [失败] 构建失败，请查看上面的 Maven 输出
        goto :fail
    )
)
echo        已就绪

REM ---------- 4. 启动基础设施 ----------
echo [4/5] 启动基础设施容器 ...
docker compose up -d >nul 2>&1
if errorlevel 1 (
    echo        [失败] 容器启动失败，请检查 docker-compose.yml
    goto :fail
)
echo        正在等待 Reranker 模型加载（首次约 1-3 分钟）...
set /a WAIT=0
:wait_reranker
curl -s -m 3 http://localhost:8001/health 2>nul | findstr /c:"UP" >nul 2>&1
if not errorlevel 1 goto reranker_ok
set /a WAIT+=3
if %WAIT% GEQ 180 (
    echo        [警告] Reranker 180 秒内未就绪，继续启动应用
    echo               检索仍可用，精排会降级为混合检索结果
    goto check_ollama
)
timeout /t 3 /nobreak >nul
goto wait_reranker
:reranker_ok
echo        Reranker 就绪

:check_ollama
echo        检查 Ollama 模型 ...
curl -s -m 5 http://localhost:11434/api/tags 2>nul | findstr /c:"qwen3:4b" >nul 2>&1
if errorlevel 1 (
    echo        [警告] Ollama 未运行或缺少 qwen3:4b 模型
    echo               请启动 Ollama 后执行：ollama pull qwen3:4b
    echo               应用仍会启动，但问答功能可能不可用
) else (
    echo        正常
)

REM ---------- 5. 启动应用 ----------
echo [5/5] 启动应用 ...
echo.

netstat -ano | findstr ":8080" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo ============================================================
    echo   [提示] 8080 端口已被占用，应用可能已经在运行
    echo.
    echo   如果确认要重启，请先关闭已有的应用窗口
    echo   （或执行：taskkill /F /IM java.exe）
    echo ============================================================
    echo.
    pause
    exit /b 0
)

echo ============================================================
echo   启动完成后可访问：
echo.
echo   问答：  http://localhost:8080/api/chat?question=你的问题
echo   检索：  http://localhost:8080/api/knowledge/hybrid-search?query=关键词
echo   状态：  http://localhost:8080/actuator/health
echo.
echo   首次问答需加载模型，约 30-60 秒，请耐心等待
echo ------------------------------------------------------------
echo   按 Ctrl+C 停止应用（基础设施容器会继续运行）
echo ============================================================
echo.

java -jar "%APP_JAR%"

echo.
echo 应用已退出。
pause
exit /b 0

:fail
echo.
pause
exit /b 1
