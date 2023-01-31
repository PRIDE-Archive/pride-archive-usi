import configparser
import os
import uuid
import warnings
from typing import Optional

import boto3
import botocore
import botocore.config
import click
from elasticsearch import Elasticsearch
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
              }, )

pride_archive_file_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/projects/{}/files?filter=fileCategory.value==RAW" \
                         "&pageSize=100&page={}&sortDirection=DESC&sortConditions=fileName"

pride_archive_project_url = "https://www.ebi.ac.uk/pride/ws/archive/v2/projects/{}"

s3_client = None
s3_bucket_name = ''
file_download_path = ''

elastic_client = None
elastic_index = ''

def get_usi_cache(usi: str) -> dict:
    """
    Get the USI cache from the ElasticSearch
    :param usi:
    :return:
    """
    try:
        response = elastic_client.search(index=elastic_index, body={"query": {"match": {"usi": usi}}})
        if response['hits']['total']['value'] > 0:
            return json.loads(response['hits']['hits'][0]['_source']['cache'])
    except Exception as e:
        warnings.warn("Error getting the USI cache from ElasticSearch: {}".format(e))
    return None

def save_usi_cache(usi: str, cache):
    """
    Save the USI cache in the ElasticSearch
    :param usi:
    :param cache:
    :return:
    """
    cache_string = json.dumps(cache)
    elastic_client.index(index=elastic_index, body={"usi": usi, "cache": cache_string})

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
    collection_name = get_collection_name(collection_name)
    page = 0
    # Query the API to get the json results, using request parameters
    url = pride_archive_file_url.format(project_accession, page)
    project_files = get_files_from_url(url)

    for file in project_files:
        if "{}.{}".format(collection_name, "raw").lower() == file.lower():
            return file
    return None

def get_collection_name(filename: str) -> Optional[str]:
    """
    Get the collection name from the file name
    :param filename:
    :return:
    """
    if filename is not None:
        return filename.replace(".raw", "").replace(".RAW", "").replace(".mzML", "")
    return None

def get_pride_archive_project_publication_date(project_accession):
    """
    Get the publication date of the project from the PRIDE archive API
    :param project_accession:
    :return:
    """
    url = pride_archive_project_url.format(project_accession)
    response = requests.get(url)
    if response.status_code == 200:
        json_response = response.json()
        if 'publicationDate' in json_response:
            return json_response['publicationDate']
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
        publication_date = get_pride_archive_project_publication_date(project_accession)
        file_name = search_file_name_in_accession(project_accession, usi_list[2])
        scan = usi_list[4]
    else:
        raise HTTPException(status_code=400, detail="The USI is not valid")
    return project_accession, publication_date, file_name, scan


@app.get("/spectrum")
async def extract_spectrum(usi: str = None):
    """
    Extract spectrum from a file using ThermoRawFileParser
    """
    (project_accession, publication_date, pride_file_name, scan_number) = get_pride_file_name(usi)

    canonical_usi = "mzspec:{}:{}:scan:{}".format(project_accession, get_collection_name(pride_file_name), scan_number)
    cache_usi = get_usi_cache(canonical_usi)
    if cache_usi is not None:
        return cache_usi

    if pride_file_name is None or scan_number is None or project_accession is None or publication_date is None:
        raise HTTPException(status_code=404, detail="File not found in PRIDE Archive")

    try:
        d_split = publication_date.split("-")
        s3_file = d_split[0] + '/' + d_split[1] + '/' + project_accession + '/' + pride_file_name
        local_file = file_download_path + '/' + str(uuid.uuid4()) + '.raw'
        s3_client.download_file(s3_bucket_name, s3_file, local_file)

        output = check_output(["ThermoRawFileParser.sh", "query", "-i={}".format(local_file),
                               "-n={}".format(scan_number), "-s"])
        spectrum = json.loads(output)
        save_usi_cache(canonical_usi, spectrum)
        os.remove(local_file)
        return spectrum
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def read_root():
    return JSONResponse(content=app.openapi())


@app.get("/docs")
def read_docs():
    return JSONResponse(content=app.openapi())


@app.get("/health")
def read_docs():
    return 'alive'

def get_config(file):
    """
    This method read the default configuration file config.ini in the same path of the pipeline execution
    :return:
    """
    config = configparser.ConfigParser()
    config.read(file)
    return config


@click.command()
@click.option('--config-file', '-a', type=click.Path(), default='config.ini')
@click.option('--config-profile', '-c', help="This option allow to select a config profile", default='TEST')
def main(config_file, config_profile):
    global s3_client, s3_bucket_name, file_download_path, elastic_client, elastic_index
    config = get_config(config_file)
    s3_url = config[config_profile]['S3_URL']
    s3_bucket_name = config[config_profile]['S3_BUCKET']
    http_proxy = config[config_profile]['HTTP_PROXY']
    file_download_path = config[config_profile]['FILE_DOWNLOAD_PATH']
    port = config[config_profile]['PORT']

    elastic_server_array = config[config_profile]['ELASTIC_SEARCH_SERVERS'].split(',')
    elastic_port = config[config_profile]['ELASTIC_SEARCH_PORT']
    elastic_user = config[config_profile]['ELASTIC_SEARCH_USER']
    elastic_password = config[config_profile]['ELASTIC_SEARCH_PASSWORD']
    elastic_index = config[config_profile]['ELASTIC_SEARCH_INDEX']


    os.makedirs(file_download_path, exist_ok=True)

    proxy_definitions = {
        'http': http_proxy,
        'https': http_proxy
    }

    config = botocore.config.Config(
        region_name='us-east-1',
        signature_version=botocore.UNSIGNED,
        proxies=proxy_definitions,
        retries={
            'max_attempts': 10,
            'mode': 'standard'
        }
    )

    s3_client = boto3.client(
        's3',
        endpoint_url=s3_url,
        config=config
    )

    elastic_client = Elasticsearch(
        hosts=elastic_server_array,
        port=elastic_port,
        scheme="https",
        http_auth=(elastic_user, elastic_password),
        verify_certs=False
    )

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(port))


if __name__ == "__main__":
    main()
