"""One native Linux Codex attempt, using the frozen CAD MCP configuration."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import threading

from pilot_snapshot import safe_snapshot
from pilot_alt_network import client_environment


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text):
    return re.sub(r"(?i)Bearer\s+\S+|\bsk-[A-Za-z0-9_-]{20,}|\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}", "[REDACTED]", text)


def run(plan_path, slot):
    plan = json.loads(plan_path.read_text())
    model = next(x for x in plan['models'] if x['slot'] == slot)
    output, session = Path(model['output']), Path(model['cwd'])
    evidence = output / 'run.json'
    if evidence.exists():
        raise ValueError('one attempt only; existing journal')
    env = client_environment()
    auth = subprocess.run([plan['client_binary'],'login','status'], env=env, capture_output=True)
    if auth.returncode:
        print(json.dumps({'status':'WAITING_OFFICIAL_LOGIN','attempt_used':False}))
        return 3
    if time.time() + 1800 + 600 > dt.datetime.fromisoformat('2026-09-23T12:00:00+08:00').timestamp():
        raise ValueError('insufficient complete budget plus evaluation reserve')
    for row in plan['input_files']:
        if hashlib.sha256((session/'inputs'/row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('frozen input changed')
    addendum = session/'PROMPT_ADDENDUM.md'
    if hashlib.sha256(addendum.read_bytes()).hexdigest() != plan['public_addendum_sha256']:
        raise ValueError('frozen addendum changed')
    work = output/'work'
    metadata = {'submission_id':model['run_id'].replace('/','_'),'model_slot':slot,'phase':'pilot','attempt':1,
        'status':'NOT_STARTED','model_provider':'OpenAI official Codex / ChatGPT login; client_requested',
        'model_exact_version':model['requested_model'],'invocation_mode':'CODEX_HARNESS_PILOT / native Linux CAD MCP',
        'session_id':model['run_id'],'generation_seed':None,'input_manifest_sha256':plan['input_manifest_sha256'],
        'prompt_sha256':plan['prompt_sha256'],'actual_elapsed_s':0,'feedback_rounds':0,'human_edit_minutes':0,
        'human_edits':[],'actual_cost':None,'usage_tokens':None,'unknown_fields_reason':'Backend identity, API queries, retries and billing not independently observed. CLI usage is recorded separately.','logs':['runner_log.json']}
    save(work/'operator_metadata.json',metadata)
    prompt = (session/'inputs/PROMPT.md').read_text()+'\n\n'+addendum.read_text()
    state = {'run_id':model['run_id'],'model_requested':model['requested_model'],'identity':'client_requested',
        'backend_identity':'not_independently_verified','argv':model['argv'],'cwd':str(session),'started_at_unix':time.time(),
        'classification':'STARTED','os_exit_code':None,'api_queries':None,'provider_retries':None,'count_source':'not_observed','events':[]}
    save(evidence,state)
    start = time.monotonic()
    process = subprocess.Popen(model['argv'],cwd=session,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,text=True,start_new_session=True)
    timed_out = False
    stderr_lines = []
    def consume_events():
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') in ('thread.started','turn.completed','turn.failed','error') or (
                event.get('type')=='item.completed' and event.get('item',{}).get('type') in ('agent_message','mcp_tool_call')):
                state['events'].append(json.loads(clean(json.dumps(event))))
                if event.get('type') in ('error','turn.failed') and 'fallback' in json.dumps(event).lower():
                    state['fallback_detected'] = True
                    try:
                        os.killpg(process.pid,signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                save(evidence,state)
    def consume_stderr():
        for line in process.stderr:
            stderr_lines.append(clean(line))
    readers = [threading.Thread(target=f,daemon=True) for f in (consume_events,consume_stderr)]
    for reader in readers:
        reader.start()
    try:
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except BrokenPipeError:
            pass
        process.wait(timeout=max(1,1800-(time.monotonic()-start)))
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid,signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait()
    finally:
        # The CLI's own subprocess group must not continue after this attempt.
        try:
            os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:
            pass
    for reader in readers:
        reader.join(timeout=5)
    state.update(os_exit_code=process.returncode,wall_timeout=timed_out,actual_elapsed_s=time.monotonic()-start,
                 ended_at_unix=time.time(),stderr=''.join(stderr_lines))
    tool_path = output/'tool_state.json'
    tools = json.loads(tool_path.read_text()) if tool_path.exists() else {'tool_stopped':True,'tool_calls':0,'submitted':False}
    state['tool_state'] = tools
    state['classification'] = 'MODEL_FALLBACK_REJECTED' if state.get('fallback_detected') else 'TIMEOUT' if timed_out else 'NATIVE_SUBMITTED' if tools.get('submitted') and process.returncode==0 else 'GENERATION_FAILED'
    save(evidence,state)
    try:
        state['model_final_snapshot'] = safe_snapshot(work,output/'model_final',tool_stopped=tools.get('tool_stopped') is True)
        safe_snapshot(output/'model_final',output/'operator_final')
        final = output/'operator_final'
        model_wrote_submission = (final/'submission.json').is_file()
        metadata.update(status='COMPLETED' if state['classification']=='NATIVE_SUBMITTED' and model_wrote_submission else 'GENERATION_FAILED',
                        actual_elapsed_s=state['actual_elapsed_s'])
        metadata['session_id'] = next((e['thread_id'] for e in state['events'] if e['type']=='thread.started'),model['run_id'])
        save(final/'submission.json',metadata)
        save(final/'runner_log.json',state)
        state['final_snapshot'] = safe_snapshot(final,output/'final')
        state['model_wrote_submission'] = model_wrote_submission
        state['snapshot_status'] = 'COMPLETE'
    except Exception as error:
        state.update(snapshot_status='REJECTED',snapshot_error_class=type(error).__name__)
    save(evidence,state)
    print(json.dumps({k:state[k] for k in ('run_id','classification','os_exit_code','snapshot_status','actual_elapsed_s')}))
    return 0 if state['classification']=='NATIVE_SUBMITTED' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--slot',choices=['model_A','model_B','model_C'],required=True)
    args=parser.parse_args()
    raise SystemExit(run(args.plan,args.slot))
