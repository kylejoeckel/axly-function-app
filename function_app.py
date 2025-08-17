import os, sys, json, traceback
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

def _try(modpath, name):
    try:
        mod = __import__(modpath, fromlist=["bp"])
        bp = getattr(mod, "bp")
        app.register_functions(bp)
        REGISTERED.append(name)
    except Exception as e:
        FAILURES[name] = {"error": repr(e), "trace": traceback.format_exc()}

_try("routes.auth", "auth")
_try("routes.vehicles", "vehicles")
_try("routes.conversation", "conversation")
_try("routes.diagnose", "diagnose")

@app.function_name(name="Ping")
@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", mimetype="text/plain")

@app.function_name(name="Diag")
@app.route(route="_diag", methods=["GET"])
def diag(req: func.HttpRequest) -> func.HttpResponse:
    body = json.dumps({"registered": REGISTERED, "failures": FAILURES}, ensure_ascii=False)
    return func.HttpResponse(body, status_code=200, mimetype="application/json")
