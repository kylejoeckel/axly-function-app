from typing import Union
import azure.functions as func

def cors_response(
    body: Union[str, bytes] = b"",
    status: int = 200,
    mime: str = "text/plain"
) -> func.HttpResponse:
    return func.HttpResponse(
        body=body,
        status_code=status,
        mimetype=mime,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
    )
