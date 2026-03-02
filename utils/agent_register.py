import os
import requests
import httpx
import re
import json 
from typing import Callable,Any,AsyncGenerator,Dict

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

def build_agent_registry(agent_config:dict):
    registry = {}

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
            'execute': exec_fn
        }

    return registry
