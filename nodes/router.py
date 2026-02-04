import stat
from State import ReWOO
from context import Context
from mock_router import mock_router
from utils.CoTtracer import TraceCollector

def router_api(payload:dict) -> str:
    '''
    小导航api
    '''
    #resp = requests.post(ROUTER_URL,json=payload,timeout=60).json()
    resp = mock_router(payload)
    return resp


def run_router(state:ReWOO,ctx:Context) -> dict:
    working_input = dict(state['working_input'])
    history = working_input.get('history',[])

    if state.get('active_query') is None:
        if state.get('pending_queries'):
            active_q = state['pending_queries'].pop(0)
        else:
            active_q = working_input.get('query','')
        state['active_query'] = active_q
    else:
        active_q = state['active_query']
    
    working_input['query'] = active_q

    payload = {
        'query':active_q,
        'history':history,
        'prev_intent': working_input.get('prev_intent','')
    }

    intent = router_api(payload)
    working_input['intent'] = intent

    trace = state.get('trace',TraceCollector(event_type='planning'))
    trace.add_text(f'Router: query = {active_q}, intent = {intent}')

    return {
        'working_input':working_input,
        'router_result':intent,
        'trace':trace
    }