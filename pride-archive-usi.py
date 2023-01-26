from fastapi import FastAPI, HTTPException
from subprocess import check_output
import json
from fastapi.responses import JSONResponse
import requests

app = FastAPI(title="PRIDE Archive USI",
    description="PRIDE Archive Service to retrieve Spectrum from USI",
    version="0.0.1",
    contact={
        "name": "PRIDE Team",
        "url": "https://www.ebi.ac.uk/pride/",
        "email": "pride-support@ebi.ac.uk",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },)

pride_archive_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/projects/{}/files?filter=fileCategory.value==RAW" \
                    "&pageSize=100&page={}&sortDirection=DESC&sortConditions=fileName"


def get_files_from_url(url: str) -> list:
    """
    Get the files from the URL
    :param url:
    :return:
    """
    project_files = []
    response = requests.get(url)
    if response.status_code == 200:
        json_response = response.json()
        if '_embedded' in json_response and 'files' in json_response['_embedded']:
            for pride_file in json_response['_embedded']['files']:
                if 'fileName' in pride_file:
                    project_files.append(pride_file['fileName'])
            if '_links' in json_response and 'next' in json_response['_links']:
                project_files.extend(get_files_from_url(json_response['_links']['next']['href']))
    return project_files
def search_file_name_in_accession(project_accession: str, collection_name: str):
    """
    Search for the file name in the PRIDE archive API. First the extension of the file must be removed.
    :param project_accession:
    :param collection_name:
    :return:
    """
    collection_name = collection_name.replace(".raw", "").replace(".RAW", "").replace(".mzML", "")
    page = 0
    # Query the API to get the json results, using request parameters
    url = pride_archive_url.format(project_accession, page)
    project_files = get_files_from_url(url)

    for file in project_files:
        if "{}.{}".format(collection_name,"raw").lower() == file.lower():
            return file
    return None

def get_pride_file_name(usi):
    """
    This function extracts from the USI the Project accession, the Collection name, and the scan.
    If the three elements are present, then search for the name of the file in the PRIDE archive API.
    A USI can have the following format:
    - mzspec:PXD000966:CPTAC_CompRef_00_iTRAQ_05_2Feb12_Cougar_11-10-09.mzML:scan:12298:[iTRAQ4plex]-LHFFM[Oxidation]PGFAPLTSR/3
    - mzspec:PXD000966:CPTAC_CompRef_00_iTRAQ_05_2Feb12_Cougar_11-10-09.mzML:scan:12298
    - mzspec:PXD000966:CPTAC_CompRef_00_iTRAQ_05_2Feb12_Cougar_11-10-09:scan:12298
    - mzspec:PXD000966:CPTAC_CompRef_00_iTRAQ_05_2Feb12_Cougar_11-10-09:scan:12298:[iTRAQ4plex]-LHFFM[Oxidation]PGFAPLTSR/3
    :param usi:
    :return:
    """
    if 'scan' not in usi:
        raise HTTPException(status_code=404, detail="USI does not contain scan information")

    usi_list = usi.split(":")
    if len(usi_list) > 4:
        project_accession = usi_list[1]
        file_name = search_file_name_in_accession(project_accession, usi_list[2])
        scan = usi_list[4]
    else:
        raise HTTPException(status_code=400, detail="The USI is not valid")
    return project_accession, file_name, scan


@app.get("/spectrum/")
async def extract_spectrum(usi: str = None):
    """
    Extract spectrum from a file using ThermoRawFileParser
    """
    (project_accession, pride_file_name, scan_number) = get_pride_file_name(usi)

    if pride_file_name is None or scan_number is None:
        raise HTTPException(status_code=404, detail="File not found in PRIDE Archive")

    try:
        output = check_output(["ThermorawFileparser.sh","query","-i={}".format(pride_file_name),
                               "-n={}".format(scan_number),"-s"])
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