import os, sys, json, traceback, importlib
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

if not os.getenv("WEBSITE_INSTANCE_ID"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

REGISTERED = []
FAILURES = {}

@app.function_name(name="Ping")
@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", mimetype="text/plain")

@app.function_name(name="Env")
@app.route(route="_env", methods=["GET"])
def env(req: func.HttpRequest) -> func.HttpResponse:
    keys = ["FUNCTIONS_WORKER_RUNTIME","FUNCTIONS_EXTENSION_VERSION",
            "SCM_DO_BUILD_DURING_DEPLOYMENT","ENABLE_ORYX_BUILD","WEBSITE_INSTANCE_ID"]
    body = {k: os.getenv(k) for k in keys}
    return func.HttpResponse(json.dumps(body), mimetype="application/json")

@app.function_name(name="Deps")
@app.route(route="_deps", methods=["GET"])
def deps(req: func.HttpRequest) -> func.HttpResponse:
    mods = ["sqlalchemy","openai","azure.storage.blob","jwt","cryptography"]
    out = {}
    for m in mods:
        try:
            importlib.import_module(m)
            out[m] = "ok"
        except Exception as e:
            out[m] = repr(e)
    return func.HttpResponse(json.dumps(out), mimetype="application/json")

def _do_register():
    global REGISTERED, FAILURES
    REGISTERED, FAILURES = [], {}
    for modpath, name in [
        ("routes.auth", "auth"),
        ("routes.vehicles", "vehicles"),
        ("routes.conversation", "conversation"),
        ("routes.diagnose", "diagnose"),
    ]:
        try:
            mod = __import__(modpath, fromlist=["bp"])
            app.register_functions(getattr(mod, "bp"))
            REGISTERED.append(name)
        except Exception as e:
            FAILURES[name] = {"error": repr(e), "trace": traceback.format_exc()}

@app.function_name(name="Enable")
@app.route(route="_enable", methods=["POST","GET"])
def enable(req: func.HttpRequest) -> func.HttpResponse:
    _do_register()
    return func.HttpResponse(json.dumps({"registered": REGISTERED, "failures": FAILURES}),
                             mimetype="application/json")

@app.function_name(name="Diag")
@app.route(route="_diag", methods=["GET"])
def diag(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"registered": REGISTERED, "failures": FAILURES}),
                             mimetype="application/json")
