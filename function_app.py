import azure.functions as func
import logging, os

logging.basicConfig(level=logging.INFO)
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def _is_azure():
    return bool(os.environ.get("WEBSITE_INSTANCE_ID"))

try:
    if not _is_azure():
        from dotenv import load_dotenv 
        try:
            load_dotenv()
        except Exception as e:
            logging.exception("load_dotenv() failed: %s", e)
except Exception as e:
    logging.exception("dotenv import failed (continuing without .env): %s", e)

def _register_blueprints(app: func.FunctionApp):
    def _try(modpath, name):
        try:
            mod = __import__(modpath, fromlist=["bp"])
            app.register_functions(getattr(mod, "bp"))
            logging.info("Registered %s", name)
        except Exception as e:
            logging.exception("Failed to load %s: %s", modpath, e)

    _try("routes.diagnose", "diagnose")
    _try("routes.conversation", "conversation")
    _try("routes.vehicles", "vehicles")
    _try("routes.auth", "auth")

_register_blueprints(app)

@app.function_name(name="Ping")
@app.route(route="ping", methods=["GET"])
def ping(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", status_code=200, mimetype="text/plain")
