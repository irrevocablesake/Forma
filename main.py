from pathlib import Path
import shutil
from totalsegmentator.python_api import totalsegmentator

import json

import nibabel as NIBABEL
import numpy as NUMPY
import trimesh
from skimage.measure import marching_cubes
from nibabel.affines import apply_affine

from PIL import Image

OUTPUT_FILE_NAME = "patient01"
FILE_NAME = "patient01.nii.gz"

PROJECT_DIR = Path(__file__).resolve().parents[0]
PUBLIC_DIR = PROJECT_DIR / "frontend" / "public"
INPUT_CT = PROJECT_DIR / "Medical_Dataset" / "CT" / FILE_NAME
OUTPUT_DIR = PUBLIC_DIR / OUTPUT_FILE_NAME
MASK_DIR = OUTPUT_DIR / "masks"
MESH_DIR = OUTPUT_DIR / "meshes"
MASK_PATH = MASK_DIR / "liver.nii.gz"
SLICE_PATH = OUTPUT_DIR / "preview.png"

def generate():
    if not INPUT_CT.exists():
        raise FileNotFoundError(f"CT Volume not found: { INPUT_CT }")

    if MASK_DIR.exists():
        shutil.rmtree(MASK_DIR)

    MASK_DIR.mkdir( parents=True, exist_ok= True )

    print("Running TotalSegmentator Inference...")

    totalsegmentator(
        input = str(INPUT_CT),
        output = str(MASK_DIR),
        roi_subset = ["liver"],
        device = "gpu"
    )

    if not MASK_PATH.exists():
        raise FileNotFoundError(f"Expected liver mask was not produced: { MASK_PATH }")

    return MASK_PATH

def generateMesh( mask_path : Path ):
    print("Loading Liver Mask")

    mask_image = NIBABEL.load( str( mask_path ) )
    mask = NUMPY.asarray( mask_image.dataobj ) > 0

    if not NUMPY.any( mask ):
        raise ValueError("The Liver Mask is Emtpy")

    if NUMPY.all( mask ):
        raise ValueError("The liver mask contains no exterior voxels.")

    print(f"Mask dimensions: {mask.shape}")
    print("Extracting surface with Marching Cubes...")

    vertices, faces, normals, values = marching_cubes(
        mask.astype(NUMPY.uint8),
        level=0.5,
    )

    vertices_ras = apply_affine(mask_image.affine, vertices)

    vertices_gltf = vertices_ras[:, [0, 2, 1]].copy()
    vertices_gltf[:, 2] *= -1

    mesh = trimesh.Trimesh(
        vertices=vertices_gltf,
        faces=faces,
        process=True,
    )

    mesh.fix_normals()

    MESH_DIR.mkdir(parents=True, exist_ok=True)

    mesh_path = MESH_DIR / "liver.glb"
    mesh.export(mesh_path)

    print(f"Mesh vertices: {len(mesh.vertices):,}")
    print(f"Mesh triangles: {len(mesh.faces):,}")
    print(f"Saved GLB: {mesh_path}")

    return mesh_path

def generateList():
    datasets = sorted(
        folder.name
        for folder in PUBLIC_DIR.iterdir()
        if folder.is_dir()
        and (folder / "assets.json").is_file()
    )

    with open(PUBLIC_DIR / "datasets.json", "w") as file:
        json.dump({"datasets": datasets}, file, indent=2)

    return datasets

def generateSlice():
    ct_img = NIBABEL.load( str( INPUT_CT ) )
    mask_img = NIBABEL.load( str( MASK_PATH ))

    ct = ct_img.get_fdata( dtype = NUMPY.float32 )
    mask = NUMPY.asarray( mask_img.dataobj ) > 0

    if ct.shape != mask.shape:
        raise ValueError(f"CT shape {ct.shape} does not match mask shape {mask.shape}")
    
    # slice_index = ct.shape[2] // 2

    slice_areas = NUMPY.sum(mask, axis=(0, 1))
    slice_index = int(NUMPY.argmax(slice_areas))

    ct_slice = ct[:, :, slice_index]
    mask_slice = mask[:, :, slice_index]

    window_center = 40
    window_width = 400
    low = window_center - window_width / 2
    high = window_center + window_width / 2

    gray = NUMPY.clip((ct_slice - low) / (high - low), 0, 1)
    gray = (gray * 255).astype(NUMPY.uint8)    

    rgb = NUMPY.repeat(gray[:, :, None], 3, axis=2)
    rgb[mask_slice] = (
        0.65 * rgb[mask_slice] + 0.35 * NUMPY.array([255, 40, 40])
    ).astype(NUMPY.uint8)

    rgb = NUMPY.flipud(rgb)

    SLICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(SLICE_PATH)

    print(f"Saved slice {slice_index} to {SLICE_PATH}")

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mask_path = generate()
    mesh_path = generateMesh(mask_path)

    manifest = {
        "dataset": "patient01",
        "modality": "CT",
        "organs": [
            {
                "id": "liver",
                "name": "Liver",
                "mask": "masks/liver.nii.gz",
                "mesh": "meshes/liver.glb",
            }
        ],
    }

    manifest_path = OUTPUT_DIR / "assets.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    # generateList()
    generateSlice()

    print(f"Saved manifest: {manifest_path}")
    print("Forma processing pipeline complete.")


if __name__ == "__main__":
    # main()
    generateSlice()