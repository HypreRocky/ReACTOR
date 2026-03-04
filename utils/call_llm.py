from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from conf.config import github_api_key
_llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=github_api_key, 
    base_url="https://models.inference.ai.azure.com",
    temperature = 0.01
)

def execute_react_agent(prompt: str) -> str:
    resp = _llm.invoke([
        SystemMessage(content='你是一个严格按照指令执行的智能助手。'),
        HumanMessage(content=prompt),
    ])
    return resp.content.strip()
