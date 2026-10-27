
from pathlib import Path
import hashlib
import json
import shutil

import nibabel as nib
import numpy as np
import trimesh

from nibabel.affines import apply_affine
from PIL import Image
from skimage.measure import marching_cubes
from totalsegmentator.python_api import totalsegmentator


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = PROJECT_DIR / "frontend" / "public"

DATASET_ID = "patient01"
INPUT_CT = PROJECT_DIR / "Medical_Dataset" / "CT" / f"{DATASET_ID}.nii.gz"

PATIENTS_DIR = PUBLIC_DIR / "Patients"
OUTPUT_DIR = PATIENTS_DIR / DATASET_ID

MASK_DIR = OUTPUT_DIR / "masks"
MESH_DIR = OUTPUT_DIR / "meshes"
SLICES_DIR = OUTPUT_DIR / "slices"

MANIFEST_PATH = OUTPUT_DIR / "assets.json"
PREVIEW_PATH = OUTPUT_DIR / "preview.png"


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------

def organ_name(organ_id: str) -> str:
    return organ_id.replace("_", " ").title()


def organ_color(organ_id: str) -> tuple[int, int, int]:
    """Return a stable, distinct-looking color for an organ."""
    digest = hashlib.sha256(organ_id.encode("utf-8")).digest()

    # Avoid very dark colors that are difficult to see on CT images.
    return tuple(80 + (value % 176) for value in digest[:3])


# ---------------------------------------------------------------------
# 1. Segmentation
# ---------------------------------------------------------------------

def generateMasks() -> list[Path]:
    if not INPUT_CT.is_file():
        raise FileNotFoundError(f"CT volume not found: {INPUT_CT}")

    # Remove stale segmentation output before regenerating.
    if MASK_DIR.exists():
        shutil.rmtree(MASK_DIR)

    MASK_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Running TotalSegmentator for {INPUT_CT.name}...")
    print("This will segment all supported organs.")

    totalsegmentator(
        input=str(INPUT_CT),
        output=str(MASK_DIR),
        device="gpu",
    )

    masks = sorted(MASK_DIR.glob("*.nii.gz"))

    if not masks:
        raise FileNotFoundError(
            f"TotalSegmentator did not produce masks in {MASK_DIR}"
        )

    print(f"Generated {len(masks)} masks.")
    return masks


# ---------------------------------------------------------------------
# 2. Mesh generation
# ---------------------------------------------------------------------

def generateMesh(mask_path: Path) -> Path | None:
    organ_id = mask_path.name.removesuffix(".nii.gz")
    mesh_path = MESH_DIR / f"{organ_id}.glb"

    print(f"Generating mesh: {organ_id}")

    mask_image = nib.load(str(mask_path))
    mask = np.asarray(mask_image.dataobj) > 0

    if not np.any(mask):
        print(f"Skipping empty mask: {organ_id}")
        return None

    if np.all(mask):
        print(f"Skipping mask without exterior voxels: {organ_id}")
        return None

    vertices, faces, _, _ = marching_cubes(
        mask.astype(np.uint8),
        level=0.5,
    )

    # Transform voxel coordinates to physical RAS coordinates.
    vertices_ras = apply_affine(mask_image.affine, vertices)

    # Convert RAS coordinates to the GLTF coordinate convention used by this project.
    vertices_gltf = vertices_ras[:, [0, 2, 1]].copy()
    vertices_gltf[:, 2] *= -1

    mesh = trimesh.Trimesh(
        vertices=vertices_gltf,
        faces=faces,
        process=True,
    )

    # --- ADD SMOOTHING TO ELIMINATE STAIRCASE ARTIFACTS ---
    # Taubin smoothing removes voxel grid steps without shrinking the organ volume
    trimesh.smoothing.filter_taubin(mesh, iterations=15)
    
    # Recalculate smooth vertex normals so lighting renders cleanly
    mesh.vertex_normals = None 
    mesh.fix_normals()

    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(mesh_path)

    print(
        f"Saved {mesh_path.name}: "
        f"{len(mesh.vertices):,} vertices, "
        f"{len(mesh.faces):,} triangles"
    )

    return mesh_path

# ---------------------------------------------------------------------
# 3. Generate axial, coronal, and sagittal slices
# ---------------------------------------------------------------------

def generateSlices(mask_paths: list[Path]) -> dict:
    print("Preparing CT slices in all three orientations...")

    # Convert the CT to canonical RAS orientation.
    ct_image = nib.as_closest_canonical(nib.load(str(INPUT_CT)))
    ct_data = np.asarray(ct_image.dataobj, dtype=np.float32)
    ct_shape = ct_data.shape

    if len(ct_shape) != 3:
        raise ValueError(f"Expected a 3D CT volume, got {ct_shape}")

    label_path = OUTPUT_DIR / "_labels.tmp"

    labels = np.memmap(
        label_path,
        dtype=np.uint16,
        mode="w+",
        shape=ct_shape,
    )
    labels[:] = 0

    organ_labels = []

    # Build one label volume, using the same stable organ colors.
    for label_id, mask_path in enumerate(mask_paths, start=1):
        if label_id > np.iinfo(np.uint16).max:
            raise ValueError("Too many masks for a uint16 label volume.")

        organ_id = mask_path.name.removesuffix(".nii.gz")

        mask_image = nib.as_closest_canonical(
            nib.load(str(mask_path))
        )

        if mask_image.shape != ct_shape:
            raise ValueError(
                f"Shape mismatch for {organ_id}: "
                f"{mask_image.shape} != {ct_shape}"
            )

        mask = np.asarray(mask_image.dataobj) > 0
        labels[mask] = label_id

        organ_labels.append({
            "label": label_id,
            "id": organ_id,
            "name": organ_name(organ_id),
            "color": list(organ_color(organ_id)),
        })

        del mask

    labels.flush()

    if SLICES_DIR.exists():
        shutil.rmtree(SLICES_DIR)

    # Each axis gets its own directory.
    axes = {
        "axial": {
            "count": ct_shape[2],
            "directory": SLICES_DIR / "axial",
            "pattern": "slices/axial/axial_{index:04d}.png",
        },
        "coronal": {
            "count": ct_shape[1],
            "directory": SLICES_DIR / "coronal",
            "pattern": "slices/coronal/coronal_{index:04d}.png",
        },
        "sagittal": {
            "count": ct_shape[0],
            "directory": SLICES_DIR / "sagittal",
            "pattern": "slices/sagittal/sagittal_{index:04d}.png",
        },
    }

    for axis in axes.values():
        axis["directory"].mkdir(parents=True, exist_ok=True)

    window_center = 40
    window_width = 400
    low = window_center - window_width / 2

    preview_index = 0
    max_area = -1

    def save_slice(ct_slice, label_slice, output_path):
        # Window CT values into grayscale.
        gray = np.clip(
            (ct_slice - low) / window_width,
            0,
            1,
        )
        gray = (gray * 255).astype(np.uint8)

        rgb = np.repeat(gray[:, :, None], 3, axis=2)

        # Apply exactly the same RGB assignment used for every axis.
        for organ in organ_labels:
            organ_mask = label_slice == organ["label"]

            if np.any(organ_mask):
                color = np.asarray(organ["color"], dtype=np.float32)
                rgb[organ_mask] = (
                    0.55 * rgb[organ_mask].astype(np.float32)
                    + 0.45 * color
                ).astype(np.uint8)

        image = Image.fromarray(rgb)
        image.save(output_path)
        return int(np.count_nonzero(label_slice))

    # Axial: index moves along the superior/inferior direction.
    for index in range(axes["axial"]["count"]):
        ct_slice = ct_data[:, :, index].T
        label_slice = np.asarray(labels[:, :, index]).T

        # Keep superior/anterior portions toward the top of the image.
        ct_slice = np.flipud(ct_slice)
        label_slice = np.flipud(label_slice)

        output = axes["axial"]["directory"] / f"axial_{index:04d}.png"
        area = save_slice(ct_slice, label_slice, output)

        if area > max_area:
            max_area = area
            preview_index = index
            Image.open(output).save(PREVIEW_PATH)

        if index % 25 == 0 or index == axes["axial"]["count"] - 1:
            print(f"Axial: {index + 1}/{axes['axial']['count']}")

    # Coronal: index moves from posterior to anterior.
    for index in range(axes["coronal"]["count"]):
        ct_slice = ct_data[:, index, :].T
        label_slice = np.asarray(labels[:, index, :]).T

        # Superior is at the top.
        ct_slice = np.flipud(ct_slice)
        label_slice = np.flipud(label_slice)

        output = axes["coronal"]["directory"] / f"coronal_{index:04d}.png"
        save_slice(ct_slice, label_slice, output)

        if index % 25 == 0 or index == axes["coronal"]["count"] - 1:
            print(f"Coronal: {index + 1}/{axes['coronal']['count']}")

    # Sagittal: index moves from right to left in canonical RAS data.
    for index in range(axes["sagittal"]["count"]):
        ct_slice = ct_data[index, :, :].T
        label_slice = np.asarray(labels[index, :, :]).T

        # Superior is at the top.
        ct_slice = np.flipud(ct_slice)
        label_slice = np.flipud(label_slice)

        output = axes["sagittal"]["directory"] / f"sagittal_{index:04d}.png"
        save_slice(ct_slice, label_slice, output)

        if index % 25 == 0 or index == axes["sagittal"]["count"] - 1:
            print(f"Sagittal: {index + 1}/{axes['sagittal']['count']}")

    labels.flush()
    labels._mmap.close()
    del labels
    label_path.unlink(missing_ok=True)

    print("Generated all three slice orientations.")

    return {
        "axis": "multiple",
        "shape": list(ct_shape),
        "organs": organ_labels,
        "previewIndex": preview_index,
        "preview": "preview.png",
        "views": {
            name: {
                "count": info["count"],
                "directory": f"slices/{name}",
                "pattern": info["pattern"],
            }
            for name, info in axes.items()
        },
    }

# ---------------------------------------------------------------------
# 4. Manifest
# ---------------------------------------------------------------------

def generateManifest(
    mask_paths: list[Path],
    mesh_paths: dict[str, Path],
    slice_info: dict,
) -> dict:
    organs = []

    for mask_path in mask_paths:
        organ_id = mask_path.name.removesuffix(".nii.gz")

        organ = {
            "id": organ_id,
            "name": organ_name(organ_id),
            "color": list(organ_color(organ_id)),
            "mask": f"masks/{mask_path.name}",
        }

        mesh_path = mesh_paths.get(organ_id)

        if mesh_path is not None and mesh_path.is_file():
            organ["mesh"] = f"meshes/{mesh_path.name}"

        organs.append(organ)

    manifest = {
        "dataset": DATASET_ID,
        "modality": "CT",
        "volume": {
            "shape": list(nib.load(str(INPUT_CT)).shape),
        },
        "organs": organs,
        "slices": slice_info,
    }

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"Saved manifest: {MANIFEST_PATH}")
    return manifest


# ---------------------------------------------------------------------
# 5. Main pipeline
# ---------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MESH_DIR.mkdir(parents=True, exist_ok=True)

    masks = generateMasks()

    mesh_paths = {}

    for mask_path in masks:
        mesh_path = generateMesh(mask_path)

        if mesh_path is not None:
            organ_id = mask_path.name.removesuffix(".nii.gz")
            mesh_paths[organ_id] = mesh_path

    slice_info = generateSlices(masks)

    manifest = generateManifest(
        masks,
        mesh_paths,
        slice_info,
    )

    print()
    print("Forma preprocessing complete.")
    print(f"Organs segmented: {len(masks)}")
    print(f"Meshes generated: {len(mesh_paths)}")
    print(f"Axial slices: {slice_info['views']['axial']['count']}")
    print(f"Coronal slices: {slice_info['views']['coronal']['count']}")
    print(f"Sagittal slices: {slice_info['views']['sagittal']['count']}")
    print(f"Manifest: {MANIFEST_PATH}")

    return manifest


if __name__ == "__main__":
    main()
