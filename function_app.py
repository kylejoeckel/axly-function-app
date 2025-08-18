import os, json, traceback
import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Only try dotenv locally (Azure often doesn't set WEBSITE_INSTANCE_ID; use a broader check)
IS_AZURE = bool(os.getenv("WEBSITE_SITE_NAME")) or os.getenv("FUNCTIONS_WORKER_RUNTIME") == "python"
if not IS_AZURE:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

REGISTERED: list[str] = []
FAILURES: dict[str, dict] = {}

def _try(modpath: str, name: str):
    try:
        mod = __import__(modpath, fromlist=["bp"])
        app.register_functions(getattr(mod, "bp"))
        REGISTERED.append(name)
    except Exception as e:
        FAILURES[name] = {"error": repr(e), "trace": traceback.format_exc()}

# 🔹 Register AT STARTUP so the Functions host discovers HTTP triggers
_try("routes.auth", "auth")
_try("routes.vehicles", "vehicles")
_try("routes.conversation", "conversation")
# _try("routes.diagnose", "diagnose")

@app.function_name(name="Ping")
@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", mimetype="text/plain")

# Diagnostics (read-only)
@app.function_name(name="Diag")
@app.route(route="_diag", methods=["GET"])
def diag(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"registered": REGISTERED, "failures": FAILURES}),
        mimetype="application/json"
    )
