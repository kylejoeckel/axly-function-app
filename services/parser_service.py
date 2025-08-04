from email.parser import BytesParser
from email.policy import default as default_policy

def parse_request(req):
    ctype = req.headers.get("content-type", "")
    fields = {
        "q": None, "session_id": None,
        "vehicle_id": None, 
        "make": None, "model": None, "year": None, "mods": None,
        "image": None, "audio": None
    }

    if "multipart/form-data" in ctype:
        msg = BytesParser(policy=default_policy).parsebytes(
            b"\r\n".join([f"Content-Type: {ctype}".encode(), b"", req.get_body()])
        )
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name in fields:
                content = part.get_payload(decode=True) if name in ("image", "audio") else part.get_content()
                fields[name] = content.decode() if isinstance(content, bytes) and name not in ("image", "audio") else content
    else:
        for field in fields:
            if field in ("image", "audio"):
                continue
            fields[field] = req.params.get(field)
        if not fields["q"]:
            try:
                body = req.get_json()
                for field in fields:
                    if field in body:
                        fields[field] = body[field]
            except:
                pass

    return fields
