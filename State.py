from dataclasses import dataclass, field
from typing import TypedDict,List,Dict,Any,Optional,Literal

from utils.ReACTORTracer import TraceCollector

StepType = Literal['SerialCallAgent','ParallelCallAgent','DispatchByIntent','AskUser','AppendHistory']
StepMode = Literal['serial','parallel']
 
class PlanStep(TypedDict,total=False):
    id: str
    desc: str
    type: StepType
    mode: StepMode
    group: str      # Parallel group id
    depends_on: List[str]

    agent: str
    input: Any  # $WORKING_INPUT
    
    # clarify
    key: str
    question: str

    #history
    payload_ref: str  # '#E1' or '$LAST_RESULT'


@dataclass
class StepResult:
    id: str = ""
    tag: str = ""
    desc: str = ""
    status: str = ""    # ok | fail | skipped
    error: str = ""
    output: Any = None


@dataclass
class ExecutionState:
    idx: int = 0
    steps: List = field(default_factory=list)
    results: Dict[str, StepResult] = field(default_factory=dict)     # key = '#E..'
    result_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # key = step.id

class SopRuntime(TypedDict,total=False):
    active_sop_id: str
    cursor: str     # Optional: multi-step SOP
    completed_preconditions: List[str]      # preconditions id list. <e.g: ['pc_account','pc_credit']>
    completed_steps: List[str]      # SOP step ids


@dataclass
class ReplanState:
    count: int = 0
    max_iteration_limit: int = 0   # Limit of replan times.
    last_failure: str = ""
    last_plan: str = ""
    last_results: Dict[str,Any] = field(default_factory=dict)


class ReACTOR(TypedDict,total=False):

    raw_input : dict    # imported by caller. CAN NOT BE CHANGED.
    working_input : dict 

    pending_queries : List[str]   # if the query is a complex task
    active_query : str   # Changing during processing
    task : str

    plan_string : str
    reasoning_overview : str

    # ------ Agenda Core --------
    plan_agenda: List[PlanStep]     # steps waiting to be executed (allow assert)
    executed: List[str]     # step.id which has been executed.(used to avoid repeating execution)

    execution: ExecutionState

    sop_runtime: SopRuntime
    slots: Dict[str,Any]        # User slots

    required_steps: List[PlanStep]  # Result from evaluator. Insert to agenda by replan
    last_patch: Dict[str,Any]       # Use for Debug. Check the slots or facts

    pending_question: Dict[str,Any]   

    eval_status : str   # 'DONE' | 'FAILED' | 'NEED_DETAIL' | 'NEED_REPLAN'
    trace : TraceCollector
    router_result : Any
    route: Dict[str, Any]         # Router resolved single dispatch target
    routes: List[Dict[str, Any]]  # Router resolved parallel dispatch targets
    replan : ReplanState
    result: str     # Final answer(natural language)
