import re

def parse_plan_str(plan_str:str):
    '''
    Parse the structured steps in planner output text.
    format: [(plan_text,step_var,tool_tag,tool_input),.....]
    '''
    pattern = r'Plan:\s*([^\|]+)\|\s*(#E\d+)\s*=\s*(\w+)\[(.*?)\]'
    matches = re.findall(pattern,plan_str)

    steps = []
    for plan_text,step_var,tool_tag,tool_input in matches:
        steps.append((plan_text.strip(),step_var.strip(),tool_tag.strip(),tool_input.strip()))
    
    reasoning_match = re.search(r"思考过程：(.+?)(?=Plan:)", plan_str, flags=re.S)
    reasoning_match = reasoning_match.group(1).strip() if reasoning_match else ""
    return steps,reasoning_match