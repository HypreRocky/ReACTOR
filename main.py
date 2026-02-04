from SOP.sop_registration import sop_list
from context import Context
from utils.executor_utils import build_agent_registry
from src.Config import agent_config,github_api_key
from nodes.router import router_api
from graph import build_graph
from Prompt.bank_rewoo_prompt_v3 import planner_prompt
from Prompt.bank_rewoo_prompt_v2 import bank_rewoo_solver_prompt
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage,HumanMessage
from State import ReWOO

_llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=github_api_key, 
    base_url="https://models.inference.ai.azure.com",
    temperature = 0.8
)

def llm_invoke(prompt:str) -> str:
    resp = _llm.invoke([
        SystemMessage(content='你是一个严格按照指令执行的智能助手。'),
        HumanMessage(content = prompt)
    ])
    return resp.content.strip()

tool_registry = build_agent_registry(agent_config,router_api)

ctx = Context(
    llm_invoke = llm_invoke,
    planner_prompt=planner_prompt,
    solver_prompt=bank_rewoo_solver_prompt,
    agent_config = agent_config,
    sop_list = sop_list,
    router_api=router_api,
    tool_registry=tool_registry
)

graph = build_graph(ctx)

raw_input = {
    'request_id': '',
    "query": "看看我的账户余额，给我推荐个符合我标准的理财呢",
    "history": [],
    "prev_intent": "",
    'knowledge_result':'',
    'customer_no':'',
    'intent':'',
    'enable_aigc':True,
    'is_streaming':False,
    'hotfix_query':'',
    'recursion_limit':10
}

state : ReWOO = {
    "raw_input": raw_input,
    "working_input": raw_input.copy(),
    'resloved_query':[],
    'active_query':raw_input['query'],
    "task": raw_input.get("query", ""),
    "plan_string": "",
    "reasoning_overview": "",
    "steps": [],
    "results": {},
    "trace": [],
    "result": "",
    "step_idx": 0
}