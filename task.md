# 角色定义与项目背景
你现在是“VLLM 全自动接单派单系统”的首席研发 Agent (Codex Coordinator)。你需要调度你的 Sub-Agents，从零开始搭建一个基于多模态大模型（目标适配 Qwen3.5 27B / Gemma 4）、全无人监管的 PC 端自动化客服与派单系统。
接单来源：小红书、闲鱼、抖音 PC 客户端/网页。
派单去向：微信电脑版群聊。

# 核心架构模式 (Design Patterns)
本项目必须严格遵循以下设计哲学，严禁写成强耦合的单体架构：
1. **统一事件网关模式 (OpenClaw Inspired):** 摒弃本地进程队列，全系统采用 Redis (Pub/Sub + Streams) 或 WebSocket 作为消息总线。所有平台接入端均为即插即用的无状态“插件 (Adapter)”。
2. **单线程协调器模式 (Claude Code Inspired):** 核心中枢接收到消息后，不直接操作 UI，而是由 Coordinator 拆解为具有依赖关系的 `TODO Task List`，串行下发。
3. **分布式 UI 锁 (Distributed UI Mutex):** Windows 桌面环境只有一套键鼠焦点。任何 Adapter 在执行自动化点击/输入前，必须向 Redis 申请具有超时机制的全局 UI 锁。
4. **预压缩记忆管理 (Pre-compaction):** VLLM 的上下文严禁传入大量历史截图。每次输入固定格式为：`压缩后的历史文本摘要` + `最近 5 轮原文本` + `当前最新一帧 UI 截图的 Base64`。

# 模块拆分与核心逻辑定义
请审查以下四个核心模块的设计，并作为后续开发的边界：

## Module 1: 基础设施层 (Infrastructure)
* **Message Broker:** 基于 Redis 的消息总线，定义统一的 `Unified_Event` 和 `Task_Payload` JSON 格式。
* **Global Lock Manager:** 基于 Redis `SETNX` 的分布式 UI 锁服务，包含抢占失败重试和防死锁超时释放机制。
* **Base Classes:** 定义 `BaseAdapter` 抽象类，强制要求所有端侧插件实现 `start_listening()` 和 `execute_action()` 方法。

## Module 2: 网关与状态机层 (Gateway & State)
* **10s 消息防抖 (Debounce):** 以 `UID` (平台_用户ID) 为维度。监听到新消息后启动 10 秒定时器，期间同一用户的消息全并入 Buffer，倒计时结束统一推入消息总线。
* **Memory Compactor:** 后台文本记忆压缩服务，防止 Token 爆炸。

## Module 3: 核心认知层 (Cognitive Hub)
* **Brain Agent:** 业务中枢，永远设定为“必回”逻辑（可直接承认自己是自动接单机器人）。意图分类为两类：`reply` (日常沟通) 和 `dispatch` (提取订单要素，准备派发)。
* **Checker Agent (二次核对):** 当 Brain 决定派单时，必须触发独立校验流——要求端侧最新全屏截图，由 Checker 核对提取的 JSON (货号、地址、要求等) 与截图是否一致，一致才允许流转至派单动作。

## Module 4: 平台适配器插件 (Adapters)
* 职责拆分：分为后台静默监控 (Observer，轮询抓包或无焦点截图) 和前台动作执行 (Executor，获取 UI 锁后执行 `pywinauto` / `Playwright` 动作)。
* 错误恢复：执行失败或焦点丢失时，需具备按 `ESC` 或关闭干扰弹窗的 Rollback 能力。

# 你的首要任务 (Action Required)
作为首席研发 Agent，请阅读并理解上述架构设计，然后输出：
1. **架构审核报告：** 指出上述设计中可能存在的工程隐患或缺失的基础设施组件。
2. **第一阶段开发计划：** 给出 Module 1 (基础设施与 Base 抽象类) 和 Redis 总线的具体接口/数据结构设计 (Protocol Buffers 或 Pydantic Models)，并分配给你的 Sub-Agent 开始编写底层通信骨架。

# ⚠️ 环境约束与跨 OS 拓扑说明 (Critical Environment Patch)
请注意，本系统的开发与核心运行环境为 **Arch Linux**，但目标端侧应用（如 PC 微信）必须运行在 **Windows 环境**。因此，系统必须被设计为“控制面”与“执行面”物理隔离的分布式拓扑：

1. **Linux 控制面 (Arch Linux):** - 部署 Redis Server、状态机 (State Machine)、记忆压缩器 (Memory Compactor)、大脑中枢 (Brain & Checker Agents)。
   - 这里的代码必须是纯跨平台的，严禁引入任何 Windows 独有的库（如 `win32gui`, `pywinauto`）。

2. **Windows 执行面 (VM or Remote PC):**
   - 专门部署 Module 4 (各平台 Adapters)。
   - 这里的代码可以使用 `pywinauto` 或 `uiautomation`，但必须通过网络连接到 Linux 端的 Redis。
   - 所有文件路径操作必须使用 `pathlib` 以兼容不同的操作系统路径风格。

**开发动作要求：**
在编写配置文件 (如 `.env.template` 或 `config.yaml`) 时，必须暴露 Redis 的 `HOST`、`PORT` 和 `PASSWORD` 配置项，确保 Windows 端的 Adapter 插件可以跨网段/跨宿主机连接到 Linux 的消息总线。不要默认使用 `localhost`。
