"""
Entry‑point loaded by the Azure Functions host.

It creates the singleton `FunctionApp` instance, loads shared
configuration, and registers the blueprints that hold every route.
"""
import azure.functions as func
# import logging, os
# from dotenv import load_dotenv
# import openai

# ────────────────────────────────────────────────────────────
#  Global initialisation – runs only once per Functions host
# ────────────────────────────────────────────────────────────
# load_dotenv()                                   
# # openai.api_key = os.getenv("OPENAI_API_KEY")

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("micron.autoapp")

# Create the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# ────────────────────────────────────────────────────────────
#  Register every blueprint (1 per routes/*.py file)
# ────────────────────────────────────────────────────────────
# from routes.diagnose     import bp as diagnose_bp
# from routes.conversation import bp as conversation_bp
# from routes.vehicles     import bp as vehicles_bp
# from routes.auth         import bp as auth_bp

# app.register_functions(diagnose_bp)
# app.register_functions(conversation_bp)
# app.register_functions(vehicles_bp)
# app.register_functions(auth_bp)


@app.function_name(name="Ping")
@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", status_code=200, mimetype="text/plain")