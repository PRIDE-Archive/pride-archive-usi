from fastapi import FastAPI, File, HTTPException
from subprocess import check_output
import json
from fastapi.responses import JSONResponse
from pydantic import BaseModel

class Spectrum(BaseModel):
    spectrum: dict

app = FastAPI()

@app.get("/spectrum/")
async def extract_spectrum(usi: str):
    """
    Extract spectrum from a file using ThermoRawFileParser
    """
    try:
        output = check_output(["ThermorawFileparser.sh","query","-i=/Users/yperez/work/CPTAC_CompRef_00_iTRAQ_05_2Feb12_Cougar_11-10-09.raw","-n=12298","-s"])
        spectrum = json.loads(output)
        return spectrum
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/docs")
def read_docs():
    return JSONResponse(content=app.openapi())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)