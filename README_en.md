<h1 align="center">ReACTOR v5</h1>
<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square">
  <img src="https://img.shields.io/badge/status-under--construction-orange?style=flat-square">
</p>  
<p align="center">
  <a href="README.md">中文</a> | 
  <a href="README_en.md">English</a>
</p>
A multi-agent orchestration framework based on a graph execution pipeline:

`Planner -> Worker -> Evaluator -> Replanner`

Key features include complex query decomposition, serial and parallel agent execution, SOP registration and matching, and multi-turn state continuation.

## Core Capabilities

- **Task decomposition**: The Planner supports `SplitQuery`, allowing complex tasks to be split into multiple subtasks.
- **Serial / Parallel execution**: The Worker supports both `SerialCallAgent` and `ParallelCallAgent`.
- **Context propagation**: The `AppendHistory` action writes the result of a step back into `history` so it can be used by subsequent steps.
- **SOP-driven planning**: SOPs can be registered via external configuration. When an SOP is matched, the planner generates plans based on the SOP instead of using the generic planning logic.
- **Automatic quality evaluation**: The Evaluator uses an LLM to assess whether the user's request has been solved. If evaluation fails, the system triggers a replan.
- **State return**: The API returns execution state to support multi-turn continuation.
- **Full graph execution**: The service invokes the compiled graph directly instead of manually orchestrating nodes.
- **Reasoning trace**: Trace supports exposing reasoning steps externally. The reasoning process is generated synchronously by the Planner and triggered during Worker execution, without needing to be written again.
- **Asynchronous execution**: Graph nodes are registered as async functions, enabling parallel worker execution.

## Node Responsibilities

| Node | Description |
|-----|-------------|
| Planner | Generates executable plans; prioritizes registered SOP matching; supports complex query decomposition. |
| Worker | Executes plan actions, routes agents, handles serial/parallel scheduling, writes results back to state, and marks failures quickly. |
| Evaluator | Uses an evaluator prompt to determine whether the user problem has been solved; if not, it generates hints and triggers replanning. |
| Replanner | Generates a new plan based on previous failures, the previous plan, and execution results. |
| Solver | Organizes the final output after graph execution (streaming or non-streaming). This node is outside the main graph. |

## Plan Action Constraints

The Planner can only output the following actions:

- `SplitQuery[...]`
- `SerialCallAgent['{"agent":"<name>","input":"$WORKING_INPUT", ...}']`
- `ParallelCallAgent['[{"agent":"<name>","input":"$WORKING_INPUT", ...}, ...]']`
- `AppendHistory['#E?']`
- `AskUser['{"question":"...","key":"..."}']`
- `FinalOutput['#E?']`

## Agent Registration

Agents are registered in `conf/config.py` under `agent_config`.

Supported types:

- `type=http`
- `type=http_async`
- `type=local`

Agent invocation only distinguishes between synchronous and asynchronous execution.  
`is_streaming` only affects the final framework output and does not affect the agent invocation method.

## Evaluation Switch

Evaluator and Replanner are enabled by default. They can be disabled via code:

```python
from Service import AgentReACTORPlanner

planner = AgentReACTORPlanner()
planner.set_evaluator(False)
```
When disabled, execution proceeds directly to the final output after the Worker finishes, skipping Evaluator and Replanner.

## Future Improvements
- More customizable solver output composition (including a2ui support)
- Skill registration and invocation alongside agents
- Memory
- Self-refinement mechanisms
- Performance optimization and configurable execution switches
