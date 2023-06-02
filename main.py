"""HeaRT endpoint."""
import traceback
from datetime import datetime
from typing import Union

import requests
from fastapi import FastAPI
from pydantic import BaseModel
from tinydb import TinyDB

from entity_types import Document
from recover_omit import recover_all
from visualise_time import main_lib


class Req(BaseModel):
    text: str
    dct: Union[str, None]


app = FastAPI(debug=True)

db = TinyDB("db.json")

JAMIE = os.environ["JAMIE_ENDPOINT"]  # Please specify a JaMIE endpoint URL here.


def process_time(text: str, dct: Union[str, None] = None):
    try:
        res_jamie = requests.get(JAMIE, params={"text": text}).json()
    except:
        return {
            "status": "Failed",
            "message": "JaMIE endpoint is dead:\n" + traceback.format_exc(),
        }
    if res_jamie["status"] != "Success":
        return {
            "status": "Failed",
            "message": "JaMIE endpoint returns an error:\n" + res_jamie["error"],
        }
    if not res_jamie["text"]:
        return {
            "status": "Failed",
            "message": "JaMIE returned nothing, without explicit failure.",
        }
    xml_text = "\n".join(res_jamie["text"])
    try:
        doc = Document.from_xml(xml_text)
    except:
        return {
            "status": "Failed",
            "message": "JaMIE returned invalid XML:\n" + xml_text,
        }
    try:
        recover_all(doc)
    except:
        return {
            "status": "Failed",
            "message": "Failted to recover omitted entities and relations:\n"
            + xml_text,
        }
    try:
        res_time = main_lib(doc, dct)
    except Exception:
        return {
            "status": "Failed",
            "message": "Timeline processing failed:\n" + traceback.format_exc(),
        }
    db.insert(
        {
            "created_at": datetime.now().isoformat(),
            "text": text,
            "dct": dct,
            "results": res_time,
        }
    )
    return {"status": "Success", "response": res_time}


@app.get("/")
async def root(text: str, dct: Union[str, None] = None):
    return process_time(text, dct)


@app.post("/")
async def root_post(req: Req):
    return process_time(req.text, req.dct)
