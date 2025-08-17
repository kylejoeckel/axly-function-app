import os, sys, logging
import azure.functions as func

# always flush prints
print = lambda *a, **k: (__import__("builtins").print)(*a, **{**k, "flush": True})

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# local-only .env
if not os.environ.get("WEBSITE_INSTANCE_ID"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("dotenv loaded locally")
    except Exception as e:
        print(f"dotenv skipped: {e!r}")

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

def _try_register(modpath, name):
    try:
        print(f"IMPORT {modpath} ...")
        mod = __import__(modpath, fromlist=["bp"])
        bp = getattr(mod, "bp")
        app.register_functions(bp)
        print(f"REGISTERED {name}")
    except Exception as e:
        import traceback
        print(f"FAILED {modpath}: {e!r}")
        traceback.print_exc()

# isolate auth first
_try_register("routes.auth", "auth")

@app.function_name(name="Ping")
@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", status_code=200, mimetype="text/plain")
