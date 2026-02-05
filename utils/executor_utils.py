from atexit import register
from heapq import heapreplace
import os
from tkinter.constants import E
from openai.types.responses import response_code_interpreter_call_interpreting_event
import requests
import httpx
import re

def _resolve_header(headers:dict) -> dict:
    out = {}
    for k,v in (headers or {}).items():
        if isinstance(v,str) and "${" in v:
            for m in re.findall(r'\$\{([A-Z0-9_]+)\}',v):
                v = v.replace('${' + m + '}', os.getenv(m,''))
        out[k] = v
    return out

def make_http_executor(url:str,timeout:int = 20,headers:dict|None = None):
    headers = _resolve_header(headers or {})

    def _execute(payload:dict):
        resp = requests.post(url,json=payload,timeout=timeout,headers=headers)

        try:
            return resp.json()
        except Exception:
            return {'status_code': resp.status_code, 'text': resp.text}
    
    return _execute

def make_http_executor_async(url:str,timeout:int = 20,headers:dict|None = None):
    headers = _resolve_header(headers or {})

    async def _execute(payload:dict):
        async with httpx.AsyncClient(timeout=timeout,headers=headers) as client:
            resp = await client.post(url,json=payload)
            try:
                return resp.json()
            except Exception:
                return {'status_code': resp.status_code, 'text': resp.text}
    
    return _execute

def default_payload_builder(working_input:dict,slots:dict) -> dict:
    payload = dict(working_input)
    payload['slots'] = slots
    return payload

def build_agent_registry(agent_config:dict,router_api):
    registry = {}

    # regist router
    registry["RouterNode"] = {
        'description' : 'RouterNode[input]:意图识别路由器',
        'execute':router_api,
        'intent_space':[],
        'payload_builder':None
    }

    # regist agents
    for agent_name,cfg in agent_config.items():
        endpoint = cfg.get('endpoint',{})
        etype = endpoint.get('type','http')

        if etype == 'http':
            exec_fn = make_http_executor(
                url = endpoint['url'],
                timeout = endpoint.get('timeout',20),
                headers = endpoint.get('headers')
            )
        elif etype == "http_async":
            exec_fn = make_http_executor_async(
                url=endpoint["url"],
                timeout=endpoint.get("timeout", 20),
                headers=endpoint.get("headers"),
            )
        elif etype == 'local':
            exec_fn = endpoint['callable']
        else:
            raise ValueError(f'unsupported endpoint type. type={etype} for {agent_name}')
        
        registry[agent_name] = {
            'description' : cfg.get('description',''),
            'execute': exec_fn,
            'intent_space':cfg.get('intent_space',[])
        }

    return registry