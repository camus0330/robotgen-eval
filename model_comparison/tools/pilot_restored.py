"""Explicit restored_20260923_v1 admission and pilot wiring, not a new harness."""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
import pilot_batch as batch_config

from pilot_run import ROOT, KIT, CACHE, SYSTEM_PROMPT, stamp
from pilot_snapshot import safe_snapshot, SnapshotRejected
from pilot_sandbox import execute_command

BATCH = "restored_20260923_v1"
RECORD = ROOT / "model_comparison/records/pilot_20260923" / BATCH
RUNTIME = ROOT / "results/pilot_20260923" / BATCH
OUTPUT = ROOT / "outputs/pilot_20260923" / BATCH
ENDPOINT = "https://big-model.smart-agi.com/v1/chat/completions"
CANDIDATES = {"model_A": ("DeepSeek", "deepseek-v4-pro", "deepseek-v4.1-flash"),
              "model_B": ("Kimi", "kimi-k3", "kimi-k2.7"),
              "model_C": ("GLM", "glm-5.3", "glm-5.3-flash")}
ALLOWED = {model for values in CANDIDATES.values() for model in values[1:]}
DEADLINE = dt.datetime(2026, 9, 23, 4, tzinfo=dt.timezone.utc)
CLIENT = Path(sys.executable)
MULTIMODAL = r"(?s)<MSWEA_MULTIMODAL_CONTENT><CONTENT_TYPE>(.+?)</CONTENT_TYPE>(.+?)</MSWEA_MULTIMODAL_CONTENT>"
ACTIVE_PLAN = None


def activate_batch(plan):
    """One CLI process owns one explicit batch; every worker reloads its plan."""
    global ACTIVE_PLAN, BATCH, KIT, CACHE, RECORD, RUNTIME, OUTPUT, CLIENT, CANDIDATES, ALLOWED, DEADLINE
    ACTIVE_PLAN = plan
    BATCH = plan["batch_id"]
    KIT, OUTPUT, RUNTIME, RECORD = (batch_config.local(plan["paths"][k])
                                   for k in ("kit", "output_root", "results_root", "record_root"))
    CACHE = batch_config.local(plan["runtime"]["cache"])
    CLIENT = batch_config.local(plan["runtime"]["client_python"], interpreter=True)
    CANDIDATES = {s: (c["provider"], c["model"]) for s, c in plan["models"].items()}
    ALLOWED = {c["model"] for c in plan["models"].values()}
    DEADLINE = dt.datetime.fromisoformat(plan["deadline"]) if plan["deadline"] else None
    import pilot_sandbox
    pilot_sandbox.CAD_VENV = str(batch_config.local(plan["runtime"]["cad_venv"]))


def run_name(plan, slot):
    return plan["run_names"][slot] if plan.get("schema_version") == batch_config.SCHEMA else slot


def require_generation(plan, plan_path, admission_path, slot):
    if plan.get("schema_version") != batch_config.SCHEMA:
        raise ValueError("historical generation entry disabled; explicit v2 batch plan required")
    gate = batch_config.gates(plan, plan_path, admission_path, slot)
    if not gate["generation_ready"]:
        raise ValueError("generation blocked before client setup: " + gate["classification"])
    return gate


def client_environment(plan):
    # Process-only allowlist; retain the working HTTP(S)/NO_PROXY values. Never
    # inject the historical NO_PROXY='*', ALL_PROXY or Python startup paths.
    allowed = ("PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR",
               "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy")
    env = {k: os.environ[k] for k in allowed if k in os.environ}
    for config in plan["models"].values():
        name = config["api_key_env"]
        if name in os.environ:
            env[name] = os.environ[name]
    env.update(PYTHON_DOTENV_DISABLED="1", MSWEA_SILENT_STARTUP="1",
               LITELLM_LOCAL_MODEL_COST_MAP="True", LITELLM_MODE="PRODUCTION",
               MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT="1",
               ROBOTGEN_CAD_VENV=str(batch_config.local(plan["runtime"]["cad_venv"])))
    return env


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value, key=""):
    sys.path.insert(0, str(ROOT / "model_comparison/spikes"))
    from mini_swe_gateway_agent_e2e import sanitize
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(sanitize(value, [key]), ensure_ascii=False, indent=2) + "\n"
    if key and key in text:
        raise ValueError("credential sanitization failed")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def new_config(model):
    return {"schema_version":"robot-model-api-config/0.1", "provider":"smart_agi_gateway",
            "model":model, "base_url":"https://big-model.smart-agi.com", "api_path":"/v1/chat/completions",
            "api_format":"openai_chat_completions", "api_key":"", "api_key_env":"SMART_AGI_API_KEY",
            "request":{"stream":False,"timeout_s":600,"max_retries":0,"temperature":None,
                       "top_p":None,"max_tokens":None,"seed":None,"extra_body":{}}}


def write_config(path, model):
    # Config schema contains the mandatory empty api_key and request object;
    # evidence sanitization intentionally drops those keys and is unsuitable here.
    config = new_config(model)
    validate_config(config,model)
    with Path(path).open("x",encoding="utf-8") as stream:
        json.dump(config,stream,ensure_ascii=False,indent=2)


def validate_config(config, model):
    if ACTIVE_PLAN is not None:
        batch_config.validate_config(config)
        if config.get("model") != model or config not in ACTIVE_PLAN["models"].values():
            raise ValueError("model config differs from this explicit batch plan")
        return
    if model not in ALLOWED or config != new_config(model):
        raise ValueError("config must match exact reviewed endpoint, model, credential source and request policy")


def has_image(messages):
    return any(isinstance(m.get("content"), list) and any(
        isinstance(p, dict) and p.get("type") == "image_url" and
        isinstance(p.get("image_url"), dict) and str(p["image_url"].get("url", "")).startswith("data:image/png;base64,")
        for p in m["content"]) for m in messages)


def with_image(text):
    uri = "data:image/png;base64," + base64.b64encode((KIT / "inputs/assets/reference.png").read_bytes()).decode()
    return text + "\n<MSWEA_MULTIMODAL_CONTENT><CONTENT_TYPE>image_url</CONTENT_TYPE>" + uri + "</MSWEA_MULTIMODAL_CONTENT>"


def response_fields(response):
    if response is None:
        return {}
    choice = response.choices[0] if getattr(response, "choices", None) else None
    content = getattr(getattr(choice, "message", None), "content", None)
    usage = getattr(response, "usage", None)
    fields = {"returned_model":getattr(response,"model",None), "finish_reason":getattr(choice,"finish_reason",None),
              "nonempty_completion":isinstance(content,str) and bool(content.strip()), "usage":{
                  k:getattr(usage,k,None) for k in ("prompt_tokens","completion_tokens","total_tokens")},
              "response_id":getattr(response,"id",None), "image_request_accepted":True}
    return fields


def error_fields(error, key):
    from mini_swe_gateway_agent_e2e import sanitize
    status = getattr(error,"status_code",None)
    result = {"safe_exception_class":type(error).__name__, "http_status":status if type(status) is int else "not_observed"}
    body = getattr(error,"body",None)
    response = getattr(error,"response",None)
    if not isinstance(body,dict) and response is not None:
        try:
            body = response.json()
        except Exception:
            body = None
    detail = body.get("error",body) if isinstance(body,dict) else {}
    if not isinstance(detail,dict):
        detail = {"message":detail}
    for name in ("type","code","message"):
        value = detail.get(name, getattr(error,name,None))
        if value is not None:
            result["error_"+name] = str(sanitize(str(value),[key]))[:1500]
    result.setdefault("error_message", str(sanitize(str(error),[key]))[:1500])
    request_id = getattr(error,"request_id",None)
    if request_id is None and response is not None:
        request_id = getattr(response,"headers",{}).get("x-request-id")
    result["request_id"] = str(sanitize(str(request_id),[key]))[:200] if request_id else "not_observed"
    if type(error) is ValueError and "config must match" in result["error_message"]: classification = "CONFIG_VALIDATION_FAILED"
    elif status in (401,403) or "CONFIG_BLOCKED" in result["error_message"]: classification = "CONFIG_BLOCKED"
    elif "timeout" in type(error).__name__.lower(): classification = "TIMEOUT"
    elif type(error).__name__ == "FormatError": classification = "FORMAT_MISMATCH"
    elif status in (400,422) and any(x in result["error_message"].lower() for x in ("image","vision","multimodal")):
        classification = "IMAGE_REJECTED"
    elif status in (404,400,422): classification = "ACCESS_OR_PROTOCOL_FAILED"
    else: classification = "ENDPOINT_FAILED"
    result["classification"] = classification
    return result


def client_setup(model_id, config, work):
    validate_config(config, model_id)  # MUST precede credential access/imports.
    key = os.environ.get(config.get("api_key_env", "SMART_AGI_API_KEY"), "")
    if not key.strip():
        raise ValueError("CONFIG_BLOCKED: selected credential absent")
    sys.path.insert(0, str(ROOT / "model_comparison/spikes"))
    from mini_swe_gateway_agent_e2e import scrub_environment, check_cache, provenance, import_upstream
    if ACTIVE_PLAN is None:
        scrub_environment()
    else:
        env = client_environment(ACTIVE_PLAN)
        # The client retains the selected key only in memory; tools get a fresh
        # empty environment through the unchanged bubblewrap executor.
        for c in ACTIVE_PLAN["models"].values():
            env.pop(c["api_key_env"], None)
        os.environ.clear()
        os.environ.update(env)
    global_dir = work / "global-config"
    global_dir.mkdir(parents=True, exist_ok=False)
    os.environ["MSWEA_GLOBAL_CONFIG_DIR"] = str(global_dir)
    check_cache(CACHE)
    verified = provenance()
    Agent, _, Model = import_upstream(CACHE)
    kwargs = {"api_base": config["base_url"] if ACTIVE_PLAN else "https://big-model.smart-agi.com/v1",
              "api_key": key, "timeout": config["request"]["timeout_s"],
              "max_retries": 0, "num_retries": 0, "stream": False}
    for name in ("temperature", "max_tokens"):
        if config["request"].get(name) is not None:
            kwargs[name] = config["request"][name]
    model = Model(model_name="openai/"+model_id, multimodal_regex=MULTIMODAL, cost_tracking="ignore_errors",
                  model_kwargs=kwargs)
    return Agent, Model, model, key, verified


def observe_queries(Model, state, save, deadline):
    def observer(frame, event, value):
        if frame.f_code is Model._query.__code__:
            if event == "call":
                if time.monotonic() >= deadline:
                    raise TimeoutError("attempt budget exhausted before query")
                limit = state.get("budget", {}).get("max_queries")
                if limit is not None and state["client_query_calls"] >= limit:
                    raise TimeoutError("query budget exhausted before provider call")
                state["client_query_calls"] += 1
                state["query_records"].append({"started_at":stamp(), "image_url_at_model_boundary":has_image(frame.f_locals["messages"])})
                save()
            elif event == "return" and value is not None:
                state["query_records"][-1].update(response_fields(value), ended_at=stamp())
                save()
        if event == "call" and frame.f_code.co_name == "completion" and frame.f_globals.get("__name__") == "litellm.main":
            # Read only a boolean from the final completion arguments; never persist frame locals.
            if state["query_records"]:
                state["query_records"][-1]["image_url_in_completion_messages"] = has_image(frame.f_locals.get("messages",[]))
                save()
    return observer


def admission_worker(model_id, plan_path, config_path, result_path):
    plan = verify_plan(plan_path)
    assert plan["batch_id"] == BATCH and model_id in ALLOWED
    state = {"batch_id":BATCH,"request_model_id":model_id,"endpoint":ENDPOINT,"request_started_at":stamp(),
             "classification":"STARTED","client_query_calls":0,"query_records":[],"parser_pass":False,
             "provider_retries":0,"timeout_s":600,"max_tokens":None,"shell_launches":0,
             "http_status":"not_observed","request_id":"not_observed","image_request_accepted":"not_observed"}
    key = ""
    def save(): write(result_path,state,key)
    save()
    started = time.monotonic()
    try:
        _, Model, model, key, verified = client_setup(model_id,read(config_path),Path(result_path).parent)
        from mini_swe_gateway_agent_e2e import quiet_call
        state["provenance"] = verified
        marker = BATCH + "_admission"
        task = with_image("This is protocol admission only. Return exactly one mswea_bash_command block containing `echo " + marker + "`. Do not execute anything or design a robot. The attached public reference image must be accepted with this text.")
        messages = [model.format_message(role="system",content=SYSTEM_PROMPT),model.format_message(role="user",content=task)]
        previous = sys.getprofile()
        sys.setprofile(observe_queries(Model,state,save,started+600))
        try:
            message, _ = quiet_call(model.query,messages)
        finally:
            sys.setprofile(previous)
        actions = message.get("extra",{}).get("actions",[])
        state["parser_pass"] = len(actions)==1 and marker in actions[0].get("command","")
        state["parsed_command"] = actions[0].get("command","")[:500] if actions else None
        state["classification"] = "ADMITTED" if state["parser_pass"] and state["query_records"][-1].get("image_url_in_completion_messages") is True else "FORMAT_MISMATCH"
    except Exception as error:
        state.update(error_fields(error,key))
    if state["query_records"]:
        state.update({k:v for k,v in state["query_records"][-1].items() if k not in ("started_at","ended_at")})
        if state.get("finish_reason") == "length": state["classification"] = "OUTPUT_TRUNCATED"
    state.update(request_ended_at=stamp(), actual_elapsed_s=time.monotonic()-started,
                 exit_code=0 if state["classification"]=="ADMITTED" else 2)
    save()
    return state["exit_code"]


def selected(plan, admission, slot):
    if plan.get("schema_version") == batch_config.SCHEMA:
        # Binding to the plan hash is checked at all executable entrypoints.
        if batch_config.channel_gate(plan, plan["_plan_sha256"], admission, slot):
            return plan["models"][slot]["model"]
        return None
    assert plan["batch_id"] == admission["batch_id"] == BATCH
    candidates = plan["candidates"][slot][1:]
    for model in candidates:
        cases = [c for c in admission["cases"] if c["request_model_id"] == model]
        if cases:
            c = cases[0]
            if c.get("classification") == "ADMITTED" and c.get("parser_pass") is True and c.get("nonempty_completion") is True and c.get("image_url_in_completion_messages") is True and c.get("child_os_exit_code") == 0:
                return model
    return None


def admission_batch(plan_path, output):
    plan = verify_plan(plan_path)
    output = Path(output)
    if output.parent.resolve() != RECORD.resolve(): raise ValueError("admission output outside new batch")
    if output.exists(): raise ValueError("admission batch already reserved")
    result = {"batch_id":BATCH,"plan_sha256":sha(plan_path),"source":"user_provided_support_screenshot",
              "original_screenshot_file":"not_provided","cases":[],"client_query_budget":6,"started_at":stamp()}
    write(output,result)
    config_dir = Path(tempfile.mkdtemp(prefix="robotgen-restored-config-"))
    stop = False
    for level in (1,2):
        for slot, candidates in plan["candidates"].items():
            if stop or selected(plan,result,slot): continue
            if dt.datetime.now(dt.timezone.utc) >= DEADLINE: stop=True; break
            model_id = candidates[level]
            cfg = config_dir / (model_id+".json")
            write_config(cfg,model_id)
            case_dir = RUNTIME / output.stem / model_id
            case_dir.mkdir(parents=True,exist_ok=False)
            evidence = case_dir / "result.json"
            argv = [str(CLIENT),"-B","-u",str(Path(__file__).resolve()),"admit-worker","--plan",str(plan_path),"--model",model_id,"--config",str(cfg),"--result",str(evidence)]
            try:
                child = subprocess.run(argv,capture_output=True,timeout=650)
                rc = child.returncode
            except subprocess.TimeoutExpired:
                rc = 124
            case = read(evidence) if evidence.exists() else {"request_model_id":model_id,"classification":"WORKER_FAILED","client_query_calls":0}
            if case.get("classification") == "STARTED": case["classification"] = "HOST_TIMEOUT" if rc==124 else "WORKER_FAILED"
            case.update(slot=slot,declared_family=candidates[0],identity_level="gateway_declared",
                        independent_backend_attestation="not_observed",child_os_exit_code=rc,argv=argv,config_path=str(cfg))
            result["cases"].append(case)
            result["client_query_calls"] = sum(c.get("client_query_calls",0) for c in result["cases"])
            write(output,result)
            print(json.dumps({k:case.get(k) for k in ("slot","request_model_id","classification","http_status","client_query_calls","error_message")}),flush=True)
            if case["classification"] in ("CONFIG_BLOCKED","CONFIG_VALIDATION_FAILED"): stop=True
    result["selected"] = {slot:selected(plan,result,slot) for slot in CANDIDATES}
    result["ended_at"] = stamp()
    write(output,result)
    return 0 if any(result["selected"].values()) else 2


def verify_plan(plan_path):
    plan = read(plan_path)
    if plan.get("schema_version") == batch_config.SCHEMA:
        batch_config.verify(plan)
        activate_batch(plan)
        plan["_plan_sha256"] = sha(plan_path)
        return plan
    if plan["batch_id"] != BATCH or plan["candidates"] != {k:list(v) for k,v in CANDIDATES.items()}:
        raise ValueError("wrong batch/candidates")
    if sha(RECORD / "PROMPT_ADDENDUM.md") != plan["addendum_sha256"]:
        raise ValueError("public addendum changed")
    for entry in plan["input_files"]:
        if sha(KIT / "inputs" / entry["path"]) != entry["sha256"]:
            raise ValueError("canonical input changed")
    for name, expected in plan["code_sha256"].items():
        if sha(ROOT / name) != expected: raise ValueError("frozen scaffold changed")
    return plan


def preflight_batch(plan_path, admission_path, result_path=None):
    plan = verify_plan(plan_path)
    if plan.get("schema_version") == batch_config.SCHEMA:
        evidence = batch_config.gates(plan, plan_path, admission_path)
        target = result_path or RUNTIME.parent / ("preflight_" + uuid.uuid4().hex + ".json")
        if not Path(target).absolute().is_relative_to(RUNTIME.parent):
            raise ValueError("preflight evidence must stay in this batch")
        batch_config.write_new(target, evidence)
        print(json.dumps(dict(evidence, evidence_path=str(target))), flush=True)
        return evidence["exit_code"]
    admission = read(admission_path)
    if admission.get("plan_sha256") != sha(plan_path): raise ValueError("admission bound to another plan")
    models = {slot:selected(plan,admission,slot) for slot in CANDIDATES}
    ready = any(models.values())
    evidence = {"batch_id":BATCH,"classification":"READY" if ready else "ACCESS_BLOCKED",
                "exit_code":0 if ready else 2,"selected":models,"plan_sha256":sha(plan_path),
                "admission_sha256":sha(admission_path),"time":stamp()}
    write(RUNTIME / "preflight.json",evidence)
    print(json.dumps(evidence),flush=True)
    return evidence["exit_code"]


def operator_metadata(slot, model_id, run_id, state):
    return {"submission_id":run_id.replace("/","_"),"model_slot":slot,"phase":"pilot","attempt":1,
            "status":"COMPLETED" if state.get("exit_status")=="Submitted" and state.get("model_wrote_submission") is True else "GENERATION_FAILED",
            "model_provider":(ACTIVE_PLAN["models"][slot]["provider"] if ACTIVE_PLAN else "Smart AGI Gateway") + " (gateway_declared)","model_exact_version":model_id,
            "invocation_mode":"DefaultAgent text action / native Linux bubblewrap CAD", "session_id":run_id,
            "generation_seed":None,"input_manifest_sha256":sha(KIT / "records/input_manifest.json"),
            "prompt_sha256":sha(KIT / "inputs/PROMPT.md"),"actual_elapsed_s":state.get("actual_elapsed_s",0),
            "feedback_rounds":0,"human_edit_minutes":0,"human_edits":[],"actual_cost":None,"usage_tokens":None,
            "unknown_fields_reason":"Gateway route identity only; billing not observed. Actual response usage is recorded separately by runner.",
            "logs":["runner_log.json"]}


def visible_message(message, key):
    from mini_swe_gateway_agent_e2e import sanitize
    content = message.get("content")
    if isinstance(content,list):
        content = [{"type":"image_url","image_sha256":sha(KIT / "inputs/assets/reference.png")} if item.get("type")=="image_url" else item for item in content]
    return sanitize({"role":message.get("role"),"content":content,
                     "actions":message.get("extra",{}).get("actions"),
                     "returncode":message.get("extra",{}).get("returncode")},[key])


def query_timeout(budget, calls, remaining):
    if remaining <= 3 or calls >= budget["max_queries"]:
        raise TimeoutError("attempt budget exhausted")
    return min(600,remaining-3)


def pilot_worker(plan_path, admission_path, slot, config_path, run_id):
    plan = verify_plan(plan_path)
    require_generation(plan, plan_path, admission_path, slot)
    if run_id != BATCH + "/" + run_name(plan, slot):
        raise ValueError("unexpected batch/run ID")
    model_id = selected(plan,read(admission_path),slot)
    if not model_id: raise ValueError("slot not admitted by new batch evidence")
    config = read(config_path)
    validate_config(config,model_id)
    if config != plan["models"][slot]:
        raise ValueError("config belongs to another slot")
    out = OUTPUT / run_name(plan, slot)
    runtime = RUNTIME / run_name(plan, slot)
    if (runtime / "run.json").exists():
        raise ValueError("worker request journal already exists; refusing replay/overwrite")
    work = out / "work"
    work.mkdir(parents=True,exist_ok=False)
    budget = plan["budget"]
    started = time.monotonic()
    deadline = started + min(budget["wall_time_s"], (DEADLINE-dt.datetime.now(dt.timezone.utc)).total_seconds())
    state = {"batch_id":BATCH,"mode":plan["mode"],"run_id":run_id,"slot":slot,"request_model_id":model_id,
             "identity_level":"gateway_declared","independent_backend_attestation":"not_observed",
             "started_at":stamp(),"classification":"RUNNING","stage":"startup","client_query_calls":0,
             "query_records":[],"real_shell_launches":0,"tool_records":[],"fixture_calls":0,"provider_retries":0,
             "real_llm_api_calls":None,"real_llm_api_calls_source":"not_observed","tool_stopped":True,
             "budget":budget,"human_design_edits":0,"visible_messages":[]}
    state.update(plan_sha256=sha(plan_path), model_config_sha256=batch_config.config_hash(config),
                 input_kit=str(KIT), addendum_sha256=plan["addendum_sha256"], deadline=plan["deadline"])
    key = ""
    def save(): write(runtime / "run.json",state,key)
    save()
    try:
        Agent, Model, model, key, verified = client_setup(model_id,config,runtime)
        from mini_swe_gateway_agent_e2e import quiet_call
        from minisweagent.exceptions import Submitted
        state["provenance"] = verified
        # A narrow query hook enforces the remaining budget without replacing the
        # pinned _query, parser, provider, or any response.
        class BudgetModel(Model):
            def query(self, messages, **kwargs):
                self.config.model_kwargs["timeout"] = min(config["request"]["timeout_s"], query_timeout(budget,state["client_query_calls"],deadline-time.monotonic()))
                state["current_query_timeout_s"] = self.config.model_kwargs["timeout"]
                try:
                    return super().query(messages,**kwargs)
                except Exception as error:
                    state["last_error"] = error_fields(error,key)
                    save()
                    raise
        model = BudgetModel(**model.config.model_dump())
        class Environment:
            def execute(self, action, cwd="", timeout=None):
                remaining = deadline-time.monotonic()-3
                if remaining <= 0: raise TimeoutError("attempt budget exhausted before tool")
                seconds = min(60,max(1,int(remaining)))
                state["tool_stopped"] = False
                state["real_shell_launches"] += 1
                tool = {"command":action["command"],"started_at":stamp(),"timeout_s":seconds}
                state["tool_records"].append(tool)
                state["visible_messages"] = [visible_message(m,key) for m in agent.messages]
                save()
                child = execute_command(action["command"],kit=KIT,writable_output=work,seconds=seconds,cad=True)
                state["tool_stopped"] = True
                tool.update(ended_at=stamp(),os_exit_code=child.returncode,stdout=child.stdout,stderr=child.stderr)
                save()
                inspected = safe_snapshot(work)
                if not (out / "first").exists() and any(r["path"] not in ("operator_metadata.json","runner_log.json","submission.json") for r in inspected["files"]):
                    state["first_snapshot"] = safe_snapshot(work,out / "first")
                    save()
                output = child.stdout + child.stderr
                lines = child.stdout.lstrip().splitlines(keepends=True)
                if child.returncode==0 and lines and lines[0].strip()=="COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT":
                    raise Submitted({"role":"exit","content":"".join(lines[1:]),"extra":{"exit_status":"Submitted","submission":"".join(lines[1:])}})
                return {"output":output,"returncode":child.returncode,"exception_info":"" if child.returncode==0 else "isolated tool failed"}
            def get_template_vars(self,**kwargs): return kwargs
            def serialize(self): return {"info":{"environment":"native Linux bubblewrap CAD, no credentials/network"}}
        metadata = operator_metadata(slot,model_id,run_id,state)
        metadata["status"] = "NOT_STARTED"
        write(work / "operator_metadata.json",metadata)
        write(work / "runner_log.json",{"state":"RUNNING","run_id":run_id})
        task = "\n\n".join((KIT / "inputs" / name).read_text(encoding="utf-8") for name in ("PROMPT.md","TASK_SPEC.md","SUBMISSION_SPEC.md"))
        task += "\n\n" + batch_config.local(plan["paths"]["addendum"]).read_text(encoding="utf-8")
        task += "\n\nThis batch's execution limits: " + json.dumps(budget) + "; deadline=" + plan["deadline"]
        task += "\n\nOperator metadata is in /work/operator_metadata.json. Read and copy it into submission.json; the runner will finalize observed process metadata after tools stop."
        agent = Agent(model=model,env=Environment(),system_template=SYSTEM_PROMPT,instance_template="{{task}}",
                      step_limit=budget["max_queries"],wall_time_limit_seconds=budget["wall_time_s"],
                      max_consecutive_format_errors=budget["max_consecutive_format_errors"],cost_limit=budget["cost_limit"],output_path=None)
        previous = sys.getprofile()
        state["stage"] = "agent_run"
        save()
        sys.setprofile(observe_queries(Model,state,save,deadline))
        try:
            result, _ = quiet_call(agent.run,with_image(task))
            state.update(exit_status=result.get("exit_status"),submission=result.get("submission"),
                         classification="SUBMITTED" if result.get("exit_status")=="Submitted" else "GENERATION_FAILED")
        finally:
            sys.setprofile(previous)
            state["visible_messages"] = [visible_message(m,key) for m in agent.messages]
            state["agent_calls"] = agent.n_calls
            state["library_cost_estimate"] = agent.cost if agent.cost > 0 else None
            state["cost_source"] = "library_estimate_not_billing" if agent.cost > 0 else "not_observed"
    except Exception as error:
        state.update(error_fields(error,key))
    state.update(ended_at=stamp(),actual_elapsed_s=time.monotonic()-started,
                 exit_code=0 if state["classification"]=="SUBMITTED" else 2)
    save()
    return state["exit_code"]


def run_pilot(plan_path, admission_path, slot, config_path, run_id):
    plan = verify_plan(plan_path)
    require_generation(plan, plan_path, admission_path, slot)
    if read(admission_path).get("plan_sha256") != sha(plan_path): raise ValueError("admission belongs to another plan")
    model_id = selected(plan,read(admission_path),slot)
    if not model_id: raise ValueError("unadmitted slot")
    validate_config(read(config_path),model_id)
    if read(config_path) != plan["models"][slot]:
        raise ValueError("config belongs to another slot")
    if run_id != BATCH+"/"+run_name(plan, slot): raise ValueError("unexpected run id")
    runtime = RUNTIME / run_name(plan, slot)
    if (OUTPUT / run_name(plan, slot)).exists():
        raise FileExistsError("run output already exists; refusing reuse")
    runtime.mkdir(parents=True,exist_ok=False)
    argv=[str(CLIENT),"-B","-u",str(Path(__file__).resolve()),"pilot-worker","--plan",str(plan_path),
          "--admission",str(admission_path),"--slot",slot,"--config",str(config_path),"--run-id",run_id]
    start=time.monotonic()
    try:
        child=subprocess.run(argv,capture_output=True,timeout=plan["budget"]["wall_time_s"],env=client_environment(plan))
        rc=child.returncode
    except subprocess.TimeoutExpired:
        rc=124
    evidence=runtime / "run.json"
    state=read(evidence) if evidence.exists() else {"run_id":run_id,"classification":"WORKER_FAILED","client_query_calls":0}
    state.update(child_os_exit_code=rc,worker_argv=argv,parent_elapsed_s=time.monotonic()-start)
    if rc==124: state.update(classification="HOST_TIMEOUT",exit_code=124)
    out=OUTPUT / run_name(plan, slot)
    try:
        raw=safe_snapshot(out/"work",out/"model_final",tool_stopped=state.get("tool_stopped") is True)
        state["model_final_snapshot"]=raw
        safe_snapshot(out/"model_final",out/"operator_final")
        # Process metadata only. No source, design mapping or generated CAD edits.
        final=out/"operator_final"
        state["model_wrote_submission"]=(final/"submission.json").is_file()
        write(final/"submission.json",operator_metadata(slot,model_id,run_id,state))
        write(final/"runner_log.json",{k:state.get(k) for k in ("run_id","classification","visible_messages","query_records","tool_records","child_os_exit_code")})
        state["final_snapshot"]=safe_snapshot(final,out/"final")
        state["final_snapshot_path"]=str(out/"final")
        state["snapshot_status"]="COMPLETE"
    except (SnapshotRejected,OSError) as error:
        state.update(snapshot_status="REJECTED",snapshot_exception_class=type(error).__name__)
    result_code = rc if rc else (0 if state.get("snapshot_status") == "COMPLETE" and state.get("classification") == "SUBMITTED" else 2)
    state["exit_code"] = result_code
    write(evidence,state)
    print(json.dumps({k:state.get(k) for k in ("run_id","classification","child_os_exit_code","client_query_calls","real_shell_launches","snapshot_status")}),flush=True)
    return result_code


def evaluation_argv(plan, plan_path, slot, submission):
    name = run_name(plan, slot)
    return [str(CLIENT), "-B", "-u", str(ROOT / "model_comparison/tools/pilot_evaluate.py"),
            "--integration", "--mode", plan["mode"], "--batch-id", BATCH,
            "--run-id", BATCH + "/" + name + "/evaluation", "--record-id", name + "/evaluation",
            "--execution-plan", str(Path(plan_path).absolute()), "--slot", slot,
            "--kit", str(KIT), "--results-root", str(RUNTIME), "--submission", str(submission)]


def evaluate_run(plan_path, slot):
    plan = verify_plan(plan_path)
    state = read(RUNTIME / run_name(plan, slot) / "run.json")
    if state.get("plan_sha256") != sha(plan_path) or state.get("snapshot_status") != "COMPLETE":
        raise ValueError("missing frozen submission from this exact plan")
    expected = OUTPUT / run_name(plan, slot) / "final"
    if Path(state["final_snapshot_path"]) != expected or safe_snapshot(expected) != state["final_snapshot"]:
        raise ValueError("frozen submission binding changed")
    argv = evaluation_argv(plan, plan_path, slot, expected)
    if (RUNTIME / run_name(plan, slot) / "evaluation").exists() or (RUNTIME / run_name(plan, slot) / "evaluation_command.json").exists():
        raise FileExistsError("evaluation already recorded; choose a separate reviewed evaluation run")
    evaluator_env = client_environment(plan)
    for config in plan["models"].values():
        evaluator_env.pop(config["api_key_env"], None)
    child = subprocess.run(argv, capture_output=True, env=evaluator_env)
    batch_config.write_new(RUNTIME / run_name(plan, slot) / "evaluation_command.json",
                           {"argv": argv, "os_exit_code": child.returncode})
    return child.returncode


ADDENDUM = """# Restored three-model pilot: common public addendum v1

This is a new pilot revision. Only runtime versions and submission/rebuild process
rules below override conflicting old environment-lock/process text. The original
robot task, motions, materials, motor, joint and other engineering constraints in
TASK_SPEC and the public inputs remain unchanged. No existing robot answer is provided.

Runtime: WSL Ubuntu-24.04, Python 3.12.3, CadQuery 2.6.1,
cadquery-ocp 7.8.1.1.post1. The old lock's CadQuery version differs; this batch
intentionally uses the already accepted runtime, identically for all three models.
Dependencies are already installed. Do not attempt any network access or install.
Run Python with /cad/bin/python (also on PATH). /cad and /kit are read-only.
Public inputs: /kit/inputs, including templates/, motion_profile.json and
the real motor CAD /kit/inputs/assets/xl330_m288_t.step and reference.png.
Your only writable design directory is /work (the current working directory).
Scratch HOME and XDG_CONFIG_HOME are /tmp and /tmp/config. No other design is visible.
Each action runs in a fresh namespace with persistent /work, no credentials and
no external network. Tool limit: 60 seconds wall, 30 seconds CPU, bounded files.
The attempt has 3600 seconds total, at most 48 model queries, no provider retries,
and at most two consecutive native format errors. No operator design feedback.

Read all required public task and submission templates. Write submission.json
and design_manifest.json as required by the original submission interface.
Operator identity/process metadata is provided in operator_metadata.json; copy it
into submission.json. The runner later fills actual elapsed time, status and logs.
Do not invent usage, billing, time, identity or operator design edits.
runner_log.json is runner-managed process evidence. These are metadata, not CAD.

Additional common design_manifest.json fields (structure, not a robot solution):
rebuild_inputs: array of relative source/local-data file paths.
rebuild_outputs: array of relative files to be freshly generated by the build.
rebuild_excluded: optional array of relative non-build records/logs to exclude.
rebuild_command: [\"python3\", \"build.py\"] or an equivalent declared Python entrypoint.
Every existing file must be classified, except design_manifest.json and
submission.json, which the evaluator recognizes as metadata. Do not put
design_manifest.json in any of these arrays, and do not generate submission.json.
List build.py and every required local source/data file in rebuild_inputs.
Every assessed STEP/STL (assembly and all manifest parts), plus other generated
outputs, must be in rebuild_outputs. Source and output paths cannot overlap.
List operator_metadata.json and runner_log.json in rebuild_excluded, along with
any other logs/non-build files. Unknown/unclassified files cause a contract error.
All paths are relative, nonempty, contain no traversal, and must not be links.
Preexisting STEP/STL cannot be source inputs. Load the public motor STEP directly
from /kit/inputs; do not copy it into the submission as a purported source file.
The evaluator creates a new directory with only declared source/data and the
verified manifest, invokes the declared Python entrypoint, and measures newly
created files. Do not rely on old CAD outputs or change your source during build.
An exit code of zero without readable expected outputs is not a rebuild pass.
Snapshot limit: 2048 files and 256 MiB total. No symlinks/junctions/hardlinks.

Use exactly one literal mswea_bash_command block per response. Observe each tool
result before continuing. Finish using the native submit rule: a successful
command whose first stdout line is COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT,
followed by your submission message. No engineering success is inferred from
submission alone; independently measured results may fail or remain NA.
"""


def prepare_batch():
    if not CLIENT.is_file(): raise ValueError("reviewed client interpreter missing")
    RECORD.mkdir(parents=True,exist_ok=False)
    RUNTIME.mkdir(parents=True,exist_ok=False)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    check_dir=OUTPUT/"cad_import_check"
    check_dir.mkdir()
    source="import cadquery,importlib.metadata as m,sys,os,json; assert 'SMART_AGI_API_KEY' not in os.environ; print(json.dumps({'python':sys.version.split()[0],'executable':sys.executable,'cadquery':m.version('cadquery'),'cadquery_ocp':m.version('cadquery-ocp')}))"
    import shlex
    child=execute_command("/cad/bin/python -I -B -c "+shlex.quote(source),kit=KIT,writable_output=check_dir,seconds=30,cad=True)
    write(RUNTIME/"cad_import_check.json",{"argv":child.args,"os_exit_code":child.returncode,"stdout":child.stdout,"stderr":child.stderr})
    if child.returncode: raise ValueError("generation CAD import blocked")
    env=json.loads(child.stdout)
    if (env["python"],env["cadquery"],env["cadquery_ocp"]) != ("3.12.3","2.6.1","7.8.1.1.post1"):
        raise ValueError("CAD runtime version changed")
    (RECORD/"PROMPT_ADDENDUM.md").write_text(ADDENDUM,encoding="utf-8")
    code_paths=sorted((ROOT/"model_comparison/tools").glob("pilot_*.py"))
    code_paths += [ROOT/"model_comparison/spikes/mini_swe_gateway_agent_e2e.py"]
    plan={"batch_id":BATCH,"mode":"PILOT_RESTORED","execution_baseline":"1acfc0823bc35007adbe4a0131e2958885070289",
          "scaffold_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
          "frozen_input_baseline":"f1d77516e35d7191a942d842b83f7ae23bb0710b",
          "created_at":stamp(),"deadline":"2026-09-23T12:00:00+08:00","candidates":{k:list(v) for k,v in CANDIDATES.items()},
          "selection_policy":"all preferred once, then at most one same-family backup per unadmitted slot; stop shared 401/403",
          "support":{"source":"user_provided_support_screenshot","original_file":"not_provided","claimed_restored":True,
                     "quotes":["恢复了再试试","再重新试试","刚刚恢复了","这是支持的模型"],"independently_verified_at_freeze":False},
          "input_files":read(KIT/"records/input_manifest.json")["files"],"input_manifest_sha256":sha(KIT/"records/input_manifest.json"),
          "addendum_sha256":sha(RECORD/"PROMPT_ADDENDUM.md"),"system_prompt_sha256":hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
          "protocol_version":"restored-pilot-text-cad/1","identity_level":"gateway_declared",
          "independent_backend_attestation":"not_observed","environment":env,
          "code_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in code_paths},
          "evaluator_rule":"pilot-cad-20260923.2","evaluator_sha256":sha(ROOT/"model_comparison/tools/pilot_evaluate.py"),
          "client_python":str(CLIENT),"endpoint":ENDPOINT,"credential_source":"SMART_AGI_API_KEY env only",
          "budget":{"wall_time_s":3600,"max_queries":48,"provider_retries":0,"cost_limit":1.0,
                    "cost_limit_semantics":"library estimate guard, not a billing cap; unknown cost stays not_observed",
                    "max_consecutive_format_errors":2,"human_design_edits":0,"operator_feedback_rounds":0},
          "admission_query_budget":6,"admission_timeout_s":600,"admission_max_tokens":None,
          "serial_order":list(CANDIDATES),"generation_conditions_identical":True,
          "budget_selection_reason":"At freeze more than 3 full 3600-second attempts plus admission and evaluation reserve remain before noon."}
    write(RECORD/"plan.json",plan)
    print(json.dumps({"plan":str(RECORD/"plan.json"),"cad_import_os_exit_code":child.returncode,"budget":plan["budget"]}),flush=True)
    return 0


def run_batch(plan_path, admission_path):
    plan=verify_plan(plan_path)
    if plan.get("schema_version") == batch_config.SCHEMA:
        if preflight_batch(plan_path, admission_path):
            return 2
        result = 0
        for slot in plan["serial_order"]:
            rc = run_pilot(plan_path, admission_path, slot, RECORD / (slot + ".config.json"),
                           BATCH + "/" + run_name(plan, slot))
            result = result or rc
            state = read(RUNTIME / run_name(plan, slot) / "run.json")
            if state.get("snapshot_status") == "COMPLETE":
                result = evaluate_run(plan_path, slot) or result
        return result
    admission=read(admission_path)
    preflight_rc=preflight_batch(plan_path,admission_path)
    if preflight_rc: return preflight_rc
    shared_config_block=False
    for slot in plan["serial_order"]:
        model_id=selected(plan,admission,slot)
        if not model_id: continue
        if shared_config_block:
            write(RUNTIME/(slot+"_not_started.json"),{"classification":"NOT_STARTED_SHARED_CREDENTIAL_BLOCK","time":stamp()})
            continue
        if (DEADLINE-dt.datetime.now(dt.timezone.utc)).total_seconds()<plan["budget"]["wall_time_s"]+900:
            write(RUNTIME/(slot+"_not_started.json"),{"classification":"NOT_STARTED_DEADLINE","time":stamp()})
            continue
        case=next(c for c in admission["cases"] if c["request_model_id"]==model_id)
        run_id=BATCH+"/"+slot
        argv=[str(CLIENT),"-B","-u",str(Path(__file__).resolve()),"run","--plan",str(plan_path),
              "--admission",str(admission_path),"--slot",slot,"--config",case["config_path"],"--run-id",run_id]
        child=subprocess.run(argv,capture_output=True)
        state=read(RUNTIME/slot/"run.json")
        write(RUNTIME/slot/"command.json",{"argv":argv,"os_exit_code":child.returncode})
        shared_config_block=state.get("classification")=="CONFIG_BLOCKED"
        print(json.dumps({"slot":slot,"generation":state.get("classification"),"os_exit_code":child.returncode}),flush=True)
        if state.get("snapshot_status")=="COMPLETE":
            evaluate_argv=[str(CLIENT),"-B","-u",str(ROOT/"model_comparison/tools/pilot_evaluate.py"),"--integration",
                           "--mode",plan["mode"],"--run-id",run_id+"/evaluation","--submission",state["final_snapshot_path"]]
            evaluation=subprocess.run(evaluate_argv,capture_output=True)
            write(RUNTIME/slot/"evaluation_command.json",{"argv":evaluate_argv,"os_exit_code":evaluation.returncode})
            print(json.dumps({"slot":slot,"evaluation_os_exit_code":evaluation.returncode}),flush=True)
    return 0


def summarize(plan_path, admission_path):
    plan=verify_plan(plan_path)
    admission=read(admission_path)
    rows=[]
    for slot in CANDIDATES:
        model_id=selected(plan,admission,slot)
        run_file=RUNTIME/slot/"run.json"
        state=read(run_file) if run_file.exists() else {}
        skipped=RUNTIME/(slot+"_not_started.json")
        metric_file=RUNTIME/slot/"evaluation/metrics.json"
        measured=read(metric_file) if metric_file.exists() else {}
        metrics={m["metric_id"]:m for m in measured.get("metrics",[])}
        evidence=measured.get("evidence",{})
        row={"slot":slot,"request_model_id":model_id,"identity_level":"gateway_declared",
             "admission_status":"ADMITTED" if model_id else "NOT_ADMITTED",
             "generation_status":state.get("classification","NOT_STARTED"),
             "actual_elapsed_s":state.get("actual_elapsed_s",state.get("parent_elapsed_s")),
             "client_query_calls":state.get("client_query_calls",0),"actual_OS_exit":state.get("child_os_exit_code"),
             "artifact_file_count":len(state.get("final_snapshot",{}).get("files",[])),
             "file_contract_status":evidence.get("intake",{}).get("intake_status","NOT_RUN"),
             "source_only_rebuild_status":metrics.get("clean_rebuild",{}).get("status","NOT_RUN"),
             "STEP_readback_status":metrics.get("step_kernel_readback",{}).get("status","NOT_RUN"),
             "STEP_raw_results":metrics.get("step_kernel_readback",{}).get("raw_value"),
             "all_printed_parts_envelope_status":metrics.get("all_printed_parts_envelope",{}).get("status","NOT_RUN"),
             "XML_parse_status":metrics.get("urdf_mjcf_parse",{}).get("status","NOT_RUN"),
             "joint_topology_actuators":"NA","dynamics":"NA","motion":"NA","robustness":"NA",
             "missing_or_failure_reason":read(skipped)["classification"] if skipped.exists() else
                 state.get("last_error",state.get("error_message",evidence.get("failure_type","not_observed" if model_id else "new admission did not succeed"))),
             "evidence_path":str(run_file.relative_to(ROOT)) if run_file.exists() else str(admission_path.relative_to(ROOT)),
             "evidence_sha256":sha(run_file) if run_file.exists() else sha(admission_path),
             "library_cost_estimate":state.get("library_cost_estimate"),"actual_billing":"not_observed",
             "query_usage":[q.get("usage") for q in state.get("query_records",[])],
             "independent_backend_attestation":"not_observed"}
        rows.append(row)
    delivered=all(r["generation_status"]=="SUBMITTED" and r["source_only_rebuild_status"]=="PASS" for r in rows)
    summary={"batch_id":BATCH,"status":"DELIVERED_PILOT" if delivered else "PARTIAL","time":stamp(),
             "support_source":plan["support"],"admission_client_queries":admission.get("client_query_calls",0),
             "generation_client_queries":sum(r["client_query_calls"] for r in rows),"rows":rows,
             "score":None,"score_reason":"No total or subset normalization; one attempt is not a stable model ranking."}
    write(RECORD/"metrics.json",summary)
    with (RECORD/"results.csv").open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in rows)
    diagnostic=["# Restored batch next action", "", "Status: "+summary["status"],
                "Support source: user_provided_support_screenshot; no original image file was supplied.",
                "Identity: gateway_declared; independent backend attestation not_observed.", "",
                "## New request diagnostics (safe to forward to support)"]
    for case in admission["cases"]:
        diagnostic.append("- "+json.dumps({k:case.get(k,"not_observed") for k in ("request_model_id","request_started_at","request_ended_at","classification","http_status","error_type","error_code","error_message","request_id","client_query_calls")},ensure_ascii=False))
    diagnostic += ["", "No automatic further admission or regeneration is authorized by this completed batch.",
                   "Existing failed attempts remain recorded. Missing engineering results are NA/NOT_RUN, never invented zeros."]
    (RECORD/"NEXT_ACTION.md").write_text("\n".join(diagnostic)+"\n",encoding="utf-8")
    artifacts=[]
    for root in (RECORD,RUNTIME):
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name not in ("artifact_manifest.json",) and "global-config" not in path.parts:
                artifacts.append({"path":path.relative_to(ROOT).as_posix(),"size":path.stat().st_size,"sha256":sha(path)})
    for slot in CANDIDATES:
        for name in ("first","model_final","final"):
            path=OUTPUT/slot/name
            if path.is_dir():
                snapshot=safe_snapshot(path)
                artifacts.append({"path":path.relative_to(ROOT).as_posix(),"kind":"snapshot","sha256":snapshot["sha256"],"files":snapshot["files"]})
    write(RECORD/"artifact_manifest.json",{"batch_id":BATCH,"artifacts":artifacts,"time":stamp()})
    print(json.dumps({"status":summary["status"],"rows":rows},ensure_ascii=False),flush=True)
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("prepare","preflight","run","pilot-worker","run-batch","evaluate"))
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--spec",type=Path)
    p.add_argument("--model");p.add_argument("--config",type=Path);p.add_argument("--result",type=Path)
    p.add_argument("--admission",type=Path)
    p.add_argument("--slot",choices=("model_A", "model_B", "model_C"));p.add_argument("--run-id")
    a=p.parse_args()
    if a.command=="prepare":
        if a.spec is None: p.error("prepare requires --spec")
        plan = batch_config.prepare(a.spec, a.plan)
        print(json.dumps({"plan":str(a.plan),"batch_id":plan["batch_id"],"model_requests":0}))
        return 0
    if read(a.plan).get("schema_version") != batch_config.SCHEMA:
        p.error("historical implicit batch execution disabled; prepare an explicit v2 plan")
    plan = verify_plan(a.plan)
    a.admission = a.admission or RECORD / "admission.json"
    if a.command in ("run", "pilot-worker", "evaluate"):
        if a.slot not in plan["models"]: p.error("--slot must be configured in this plan")
        a.config = a.config or RECORD / (a.slot + ".config.json")
        a.run_id = a.run_id or BATCH + "/" + run_name(plan, a.slot)
    if a.command=="preflight": return preflight_batch(a.plan,a.admission,a.result)
    if a.command=="run-batch": return run_batch(a.plan,a.admission)
    if a.command=="evaluate": return evaluate_run(a.plan,a.slot)
    if a.command=="run": return run_pilot(a.plan,a.admission,a.slot,a.config,a.run_id)
    if a.command=="pilot-worker": return pilot_worker(a.plan,a.admission,a.slot,a.config,a.run_id)
    raise ValueError("unsupported command")


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"classification":"CONFIG_OR_GATE_BLOCKED", "error_class":type(error).__name__,
                          "message":str(error)}), file=sys.stderr)
        raise SystemExit(2)
