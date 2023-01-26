# PRIDE Archive USI 

This API returns the spectrum in json for a given USI. 

## ThermoRawFileParser

The API uses the [ThermoRawFileParser](https://github.com/compomics/ThermoRawFileParser) to retrirve a particular 
scan for a given USI. 

How the ThermoRawFileParser is used internally: 


```bash 
 ThermorawFileparser.sh query -i={RAW PATH} -n="{Scan Number}" -s" 
```

The output is sent to the standard output (stdout)

## How to install 

To create the conda environment for the API, run the following command: 

```bash
conda env create -f environment.yml
```

## Authors 

Yasset Perez-Riverol (@ypriverol)
Chakradhar Bandla (@chakrabandla)