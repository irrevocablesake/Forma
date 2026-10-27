# Forma

<div align="center">
<table>
  <tbody>
    <tr>
      <td>
        <img src="https://raw.githubusercontent.com/irrevocablesake/Forma/refs/heads/main/MD/hero_image.png" width="100%">
        <p style="align: center; font-style: italic; font-size: 14px; color: #555;">
          Forma - DICOM MRI Visualization
        </p>
      </td>
    </tr>
  </tbody>
</table>
</div>

## Intuition

Medical Technologies like _**CT / MRI**_ produce a series of **2D cross-sectional images** that collectively describe the internal anatomy of a patient. 

But here's the interesting part: how do we go from a stack of 2D images to an actual 3D representation of the human anatomy?

The goal of Forma is to explore this process, from medical imaging data to interactive 3D anatomical visualization, using Python, medical-image segmentation, and Three.js.

A **CT scan** is essentially a **3D volume** represented as a collection of **voxels**. Each voxel contains an intensity value corresponding to the scanned tissue. While these values provide useful information about the anatomy, they don't directly tell us which voxels belong to the liver, kidneys, lungs, or other organs.

This is where segmentation comes in.

The idea is to take a medical scan, identify the structures within it, and reconstruct those structures into 3D models that we can explore interactively.

At a high level, Forma consists of three major stages:
- **Medical Imaging:** Read and process volumetric CT data.
- **Segmentation & Reconstruction:** Identify anatomical structures and reconstruct them as 3D meshes.
- **Visualization:** Bring the resulting anatomical models into an interactive 3D environment.

## Pipeline

The overall pipeline can be thought of as follows:
- We start with a 3D CT volume, represented in **NIfTI** format (.nii.gz).
- The volume is passed through **TotalSegmentator**, which uses deep-learning-based segmentation to identify anatomical structures.
- The resulting **segmentation masks** represent individual organs as separate 3D voxel volumes.
- We then use **Marching Cubes** to extract polygonal surfaces from these voxel masks.
- The extracted geometry is transformed using the volume's spatial **affine** information so that the reconstructed meshes retain their anatomical positioning and scale.
- Each reconstructed organ is **exported** as a GLB asset, ready to be loaded into a 3D application.
- We also generate **axial CT** slices with colored segmentation overlays, allowing us to inspect the original scan alongside the segmented anatomy.
- Finally, the generated assets and their metadata are made available to the frontend.

The important distinction here is that segmentation and visualization are separate stages. The computationally expensive processing happens beforehand, while the frontend focuses on displaying and exploring the resulting data.

## Simulation
Here is a video example of the Project.

https://github.com/user-attachments/assets/486b17b4-04b3-4c8d-8a15-945e4203dda5

## Resources
- Python: Medical-image preprocessing and pipeline orchestration.
- PyTorch: Deep-learning inference.
- TotalSegmentator: Anatomical segmentation.
- Marching Cubes: Surface reconstruction from voxel masks.
- trimesh: Mesh processing and GLB export.
- Three.js: Interactive 3D visualization.
- Vite: Frontend development and asset delivery.

