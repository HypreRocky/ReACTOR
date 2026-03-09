reactor_solver_prompt = '''
我们已经制定了以下思考概要：
{reasoning_overview}

以下是完整执行计划：
{plan_str}

我们收集到的证据如下：
{evidence}

请严格依据“证据”作答，禁止自行补充、推测或编造。
若证据不足以回答，请输出：无法从工具结果中得到答案。
Answer (直接给出结论)：
'''
