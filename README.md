<h1 align="center">ReACTOR v5</h1>
<p align="center">Python 3.10+ | 库状态：在建设中 | License：Apache License 2.0</p>

一个基于 `Planner -> Worker -> Evaluator -> Replanner` 图执行的多智能体编排框架。  
特点是：复杂 query 可拆分、支持串并联 agent 调用、支持 SOP 注册与命中、支持多轮状态回传与续跑。

## 核心能力

- 复杂问题拆分：Planner 支持 `SplitQuery`，把复合任务拆成多个子任务。
- 串行/并行执行：Worker 支持 `SerialCallAgent` 与 `ParallelCallAgent`。
- 上下文衔接：支持 `AppendHistory`，将某一步结果写回 `working_input.history` 给后续步骤使用。
- SOP 优先规划：可从外部配置注册 SOP，命中后按 SOP 产出计划，不走通用 Planner 逻辑。
- 自动质量把关：Evaluator 通过模型二次评估结果是否解决用户问题，失败则 Replan。
- 状态回传：接口返回 `sop_runtime / slots / pending_question / plan_string`，支持多轮续跑。
- 完整图执行：Service 仅调用 compiled graph，不再手动逐节点编排。
- 异步化：图节点以 async 方式注册，支持并行 worker 调用场景。

## 节点功能

| 节点 | 作用 |
|---|---|
| Planner | 生成可执行 Plan；优先判断是否命中已注册 SOP；支持复杂 query 拆分。 |
| Worker | 按 Plan 执行动作，负责路由 agent、串并行调度、结果写回、异常快速标记。 |
| Evaluator | 基于 evaluator prompt 调用模型评估“是否已解决问题”；不通过则给出 hint 并触发 replan。 |
| Replanner | 基于上轮失败原因、上轮计划与结果进行重规划。 |
| Solver | 图结束后统一组织输出（可流式/非流式），不是图内节点。 |

## Plan Action 约束

Planner 输出只能使用以下 Action：

- `SplitQuery[...]`
- `SerialCallAgent['{"agent":"<name>","input":"$WORKING_INPUT", ...}']`
- `ParallelCallAgent['[{"agent":"<name>","input":"$WORKING_INPUT", ...}, ...]']`
- `AppendHistory['#E?']`
- `AskUser['{"question":"...","key":"..."}']`
- `FinalOutput['#E?']`

## SOP 注册与命中

### 1) 注册入口

在 `conf/sop_config.py` 中配置：

```python
sop_config = {
    "base_dir": BASE_DIR,
    "sops": [
        {"path": "sop/mock_prd_sop.yaml", "triggers": ["存款", "定期"]},
        {"path": "sop/mock_loan_sop.yaml"},
    ],
}
```

说明：

- `path` 支持相对 `base_dir` 或绝对路径，适合注册外部定义的 SOP。
- `triggers` 可覆盖/补充 YAML 内触发词。
- Planner 会基于 query/history 进行 SOP 命中判断，命中后优先使用 SOP 规划。

### 2) 多轮 SOP 续跑

每轮把服务返回的 `sop_runtime` 与 `slots` 传回下一轮 `working_input`，可继续从上次状态运行。

## Agent 注册

在 `conf/config.py` 的 `agent_config` 中注册，支持：

- `type=http`
- `type=http_async`
- `type=local`

调用 agent 只区分同步/异步；`is_streaming` 仅影响框架最终输出，不影响 agent 调用方式。

## 评估开关

默认开启 Evaluator/Replanner。可通过代码关闭：

```python
from Service import AgentReACTORPlanner

planner = AgentReACTORPlanner()
planner.set_evaluator(False)
```

关闭后，worker 结束将直接进入最终输出，不走 evaluator/replanner。

## 启动与调用

### 1) 启动服务

```bash
python3 Service.py
```

默认地址：`http://127.0.0.1:8080`

### 2) 非流式接口

- `POST /plan`
- 入参：完整 `working_input`
- 出参：
  - `result`
  - `sop_runtime`
  - `slots`
  - `pending_question`
  - `plan_string`

### 3) 流式接口（SSE）

- `POST /plan/stream`
- 事件：
  - `final`：最终输出分片
  - `state`：状态回传（`sop_runtime/slots/pending_question/plan_string`）
  - `done`：结束事件

### 4) Demo 脚本

```bash
python3 demo_call_plan.py "帮看下最近的市场热点，再推荐个产品"
python3 demo_call_plan.py "帮看下最近的市场热点，再推荐个产品" --stream
python3 demo_call_plan.py "继续" --state-file /tmp/reactor_state.json
```

`--state-file` 会自动保存/加载 `sop_runtime` 与 `slots`，方便本地多轮续跑。

## 输出编排

Solver 按 `src/output_config.py` 组装最终输出，支持 section：

- `agent`
- `summary`
- `text`
- `final`

## 调试与日志

- 节点日志：`log/reactor_YYYYMMDD.log`（JSONL）
- 本地调试打印包含：节点耗时、路由流转、worker step 输入输出、trace 最新更新。

## 关键文件

- `graph.py`：图构建与路由
- `Service.py`：服务入口（调用 compiled graph）
- `node/planner.py`
- `node/worker.py`
- `node/evaluator.py`
- `node/replanner.py`
- `node/solver.py`
- `utils/sop_registry.py` / `utils/sop_engine.py`
- `conf/config.py` / `conf/sop_config.py`
