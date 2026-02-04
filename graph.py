from functools import partial
from langgraph.graph import StateGraph,START,END
from State import ReWOO
from context import Context
from nodes.planner import run_planner
from nodes.router import run_router
from nodes.worker import run_worker
from nodes.evaluator import run_evaluator
from nodes.replanner import run_replanner

def build_graph(ctx:Context):
    graph = StateGraph(ReWOO)
    graph.add_node('planner',partial(run_planner,ctx=ctx))
    graph.add_node('router',partial(run_router,ctx=ctx))
    graph.add_node('worker',partial(run_worker,ctx=ctx))
    graph.add_node('evaluator',partial(run_evaluator,ctx=ctx))
    graph.add_node('replanner',partial(run_replanner,ctx=ctx))

    def _route(state:ReWOO):
        if state.get('eval_status') in ('FAILED' , 'NEED_USER'):
            return 'evaluator'
        if state.get('plan_agenda'):
            return 'worker'
        return 'evaluator'
    
    def _how_end(state:ReWOO):
        if state.get('eval_status') in ('DONE' , 'FAILED' , 'NEED_USER'):
            return 'END'
        if state.get('eval_status') == 'NEXT_QUERY':
            return 'router'
        return 'replanner'
    
    graph.add_edge(START,'planner')
    graph.add_edge('planner','router')
    graph.add_edge('router','worker')
    graph.add_conditional_edges('worker',_route,{
        'worker':'worker',
        'evaluator':'evaluator'
    })
    graph.add_conditional_edges('evaluator',_how_end,{
        'router':'router',
        'replanner':'replanner',
        'END':END
    })
    graph.add_edge('replanner','worker')