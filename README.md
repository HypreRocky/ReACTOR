<h1 align="center">ReACTOR</h1>

<p align="center">
  <b>显式规划的 Planner →  Worker → Solver 多智能体执行框架</b>
</p>

<p align="center">
  <a href="./README.md">简体中文</a> | <a href="./README.en.md">English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" />
  <img src="https://img.shields.io/badge/architecture-ReWOO-orange" />
  <img src="https://img.shields.io/badge/status-under--construction-yellow" />
  <img src="https://img.shields.io/badge/license-Apache--2.0-green" />
</p>

---

## 项目简介

本项目实现了一个 **Planner → Router → Worker** 的显式规划型多智能体框架，  
支持计划生成、执行编排、结果验证与统一输出调度（Solver）。

系统强调：

- 显式可执行计划（Explainable Plan）
- 确定性调度（Deterministic Routing）
- 布局驱动输出（Layout-driven Output）
- 延迟回放流式结果（Deferred Streaming Replay）

> [!NOTE]
> 路由逻辑完全由 **Planner** 决定，Router 不进行意图识别或动态选择。

---

## 架构概览

核心组件：

- **Planner**：生成可执行 Plan、支持将复杂意图query拆分、规划串/并行逻辑。
- **Router**：根据 Plan 进行路由调度。
- **Worker**：执行 Agent 调用。
- **Evaluator / Replanner**：校验结果并在必要时重规划。
- **Solver**：按布局规则统一组装最终输出，支持从外部定义答案编排。

主要入口：

- Graph：`graph.py`
- 服务：`Service.py`
- 节点：`node/`

---

库仍在建设中。
