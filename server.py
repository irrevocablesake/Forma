import main

from flask import Flask

app = Flask( __name__ )

@app.get("/api/datasets")
def get_datasetList():    
    return main.generateList()

@app.get("/api/metadata")
def get_metadata( dataset : str ):
    mask_path = main.generate()
    mesh_path = main.generateMesh( mask_path )

@app.get("/api/organ")
def get_organ( dataset : str, organ : str ):
    pass

@app.get("/api/slice")
def get_slice( dataset : str, axis : chr, index : int ):
    pass

if __name__ == "__main__":
    app.run( debug = True )