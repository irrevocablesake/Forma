import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const DATASET_URL = '/Patients/patient01/';
const MANIFEST_URL = `${DATASET_URL}assets.json`;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x151922);

const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 10000);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight - 48, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setScissorTest(true);
document.body.style.margin = '0';
document.body.style.overflow = 'hidden';
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// --- 3D STUDIO LIGHTING ---
scene.add(new THREE.HemisphereLight(0xffffff, 0x475569, 2.5));

const keyLight = new THREE.DirectionalLight(0xffffff, 2.0);
keyLight.position.set(200, 300, 250);
scene.add(keyLight);

const fillLight = new THREE.DirectionalLight(0x93c5fd, 1.0);
fillLight.position.set(-200, 100, -100);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xf8fafc, 1.5);
rimLight.position.set(0, -200, -250);
scene.add(rimLight);

const gltfLoader = new GLTFLoader();
const textureLoader = new THREE.TextureLoader();
const organModels = new Map();

const slicePlanes = {
  axial: null,
  coronal: null,
  sagittal: null,
};

const sliceViews = {
  axial: {
    count: 0,
    index: 0,
    scene: new THREE.Scene(),
    camera: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10),
    mesh: null,
    texture: null,
    directory: '',
    pattern: '',
  },
  coronal: {
    count: 0,
    index: 0,
    scene: new THREE.Scene(),
    camera: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10),
    mesh: null,
    texture: null,
    directory: '',
    pattern: '',
  },
  sagittal: {
    count: 0,
    index: 0,
    scene: new THREE.Scene(),
    camera: new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10),
    mesh: null,
    texture: null,
    directory: '',
    pattern: '',
  },
};

for (const view of Object.values(sliceViews)) {
  view.camera.position.z = 2;
}

function getOrganColor(rgb) {
  if (!Array.isArray(rgb) || rgb.length !== 3) {
    return new THREE.Color(0xcccccc);
  }

  const hex = rgb
    .map((channel) =>
      Math.max(0, Math.min(255, Math.round(channel)))
        .toString(16)
        .padStart(2, '0'),
    )
    .join('');

  return new THREE.Color(`#${hex}`);
}

function applyOrganColor(model, rgb) {
  const color = getOrganColor(rgb);

  model.traverse((object) => {
    if (!object.isMesh) return;

    object.castShadow = true;
    object.receiveShadow = true;

    const materials = Array.isArray(object.material)
      ? object.material
      : [object.material];

    const coloredMaterials = materials.map((original) => {
      const material = original.clone();
      material.color.copy(color);
      material.vertexColors = false;
      material.needsUpdate = true;
      return material;
    });

    object.material = Array.isArray(object.material)
      ? coloredMaterials
      : coloredMaterials[0];
  });
}

function getSlicePath(view, index) {
  const paddedIndex = String(index).padStart(4, '0');
  return view.pattern.replace('{index:04d}', paddedIndex);
}

function updateSliceLabels() {
  const axialLabel = document.getElementById('label-axial');
  const coronalLabel = document.getElementById('label-coronal');
  const sagittalLabel = document.getElementById('label-sagittal');

  if (axialLabel) axialLabel.textContent = `Axial View (${sliceViews.axial.index + 1} / ${sliceViews.axial.count})`;
  if (coronalLabel) coronalLabel.textContent = `Coronal View (${sliceViews.coronal.index + 1} / ${sliceViews.coronal.count})`;
  if (sagittalLabel) sagittalLabel.textContent = `Sagittal View (${sliceViews.sagittal.index + 1} / ${sliceViews.sagittal.count})`;
}

function loadSliceTexture(view, index) {
  if (index < 0 || index >= view.count) return;

  view.index = index;
  updateSliceLabels();

  const path = getSlicePath(view, index);
  const url = new URL(path, new URL(DATASET_URL, window.location.origin)).href;

  textureLoader.load(
    url,
    (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.minFilter = THREE.LinearFilter;
      texture.magFilter = THREE.LinearFilter;

      if (view.texture) view.texture.dispose();

      view.texture = texture;
      view.mesh.material.map = texture;
      view.mesh.material.needsUpdate = true;

      const imageAspect = texture.image.width / texture.image.height;
      const viewportAspect = getViewportAspect();

      if (imageAspect > viewportAspect) {
        view.mesh.scale.set(1, viewportAspect / imageAspect, 1);
      } else {
        view.mesh.scale.set(imageAspect / viewportAspect, 1, 1);
      }

      for (const [name, v] of Object.entries(sliceViews)) {
        if (v === view) {
          updateSlicePlanePosition(name);
          break;
        }
      }
    },
    undefined,
    (error) => console.error(`Failed to load ${path}`, error),
  );
}

function getViewportAspect() {
  const width = window.innerWidth / 2;
  const height = (window.innerHeight - 48) / 2;
  return width / height;
}

function setupSliceView(view, info) {
  view.count = info.count;
  view.pattern = info.pattern;

  const material = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    map: null,
    toneMapped: false,
  });

  view.mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  view.scene.add(view.mesh);

  loadSliceTexture(view, 0);
}

function setupSlicePlanes() {
  const bounds = new THREE.Box3();
  for (const model of organModels.values()) {
    bounds.expandByObject(model);
  }

  if (bounds.isEmpty()) return;

  const size = bounds.getSize(new THREE.Vector3());

  slicePlanes.axial = new THREE.Mesh(
    new THREE.PlaneGeometry(size.x * 1.2, size.y * 1.2),
    new THREE.MeshBasicMaterial({ color: 0x3b82f6, transparent: true, opacity: 0.2, side: THREE.DoubleSide, depthWrite: false })
  );
  scene.add(slicePlanes.axial);

  slicePlanes.coronal = new THREE.Mesh(
    new THREE.PlaneGeometry(size.x * 1.2, size.z * 1.2),
    new THREE.MeshBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.2, side: THREE.DoubleSide, depthWrite: false })
  );
  slicePlanes.coronal.rotation.x = Math.PI / 2;
  scene.add(slicePlanes.coronal);

  slicePlanes.sagittal = new THREE.Mesh(
    new THREE.PlaneGeometry(size.y * 1.2, size.z * 1.2),
    new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.2, side: THREE.DoubleSide, depthWrite: false })
  );
  slicePlanes.sagittal.rotation.y = Math.PI / 2;
  scene.add(slicePlanes.sagittal);

  updateAllSlicePlanePositions();
}

function updateSlicePlanePosition(viewName) {
  const plane = slicePlanes[viewName];
  const view = sliceViews[viewName];
  if (!plane || view.count <= 1) return;

  const bounds = new THREE.Box3();
  for (const model of organModels.values()) {
    bounds.expandByObject(model);
  }

  const progress = view.index / (view.count - 1);
  const center = bounds.getCenter(new THREE.Vector3());

  if (viewName === 'axial') {
    const zPos = THREE.MathUtils.lerp(bounds.min.z, bounds.max.z, progress);
    plane.position.set(center.x, center.y, zPos);
  } else if (viewName === 'coronal') {
    const yPos = THREE.MathUtils.lerp(bounds.min.y, bounds.max.y, progress);
    plane.position.set(center.x, yPos, center.z);
  } else if (viewName === 'sagittal') {
    const xPos = THREE.MathUtils.lerp(bounds.min.x, bounds.max.x, progress);
    plane.position.set(xPos, center.y, center.z);
  }
}

function updateAllSlicePlanePositions() {
  updateSlicePlanePosition('axial');
  updateSlicePlanePosition('coronal');
  updateSlicePlanePosition('sagittal');
}

async function loadManifestAndModels() {
  const response = await fetch(MANIFEST_URL);

  if (!response.ok) {
    throw new Error(`Failed to load manifest: ${response.status}`);
  }

  const manifest = await response.json();

  if (!Array.isArray(manifest.organs)) {
    throw new Error('Manifest does not contain an organs array.');
  }

  const organsWithMeshes = manifest.organs.filter((organ) => organ.mesh);

  const results = await Promise.allSettled(
    organsWithMeshes.map(async (organ) => {
      const meshURL = new URL(
        organ.mesh,
        new URL(DATASET_URL, window.location.origin),
      );

      const gltf = await gltfLoader.loadAsync(meshURL.href);
      const model = gltf.scene;
      model.name = organ.id;

      applyOrganColor(model, organ.color);
      scene.add(model);
      organModels.set(organ.id, model);
    }),
  );

  for (const result of results) {
    if (result.status === 'rejected') {
      console.error('Failed to load an organ GLB:', result.reason);
    }
  }

  if (organModels.size === 0) {
    throw new Error('No GLB models could be loaded.');
  }

  frameModels();
  setupSlicePlanes();

  if (!manifest.slices?.views) {
    throw new Error('The manifest has no three-axis slice metadata.');
  }

  for (const [name, view] of Object.entries(sliceViews)) {
    const info = manifest.slices.views[name];
    if (!info) {
      throw new Error(`Missing slice metadata for ${name}.`);
    }
    setupSliceView(view, info);
  }
  
  updateSliceLabels();
}

function frameModels() {
  const bounds = new THREE.Box3();

  for (const model of organModels.values()) {
    bounds.expandByObject(model);
  }

  if (bounds.isEmpty()) return;

  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z);

  controls.target.copy(center);

  const distance =
    (maxDimension / 2) /
    Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));

  camera.position.set(
    center.x + distance * 0.15,
    center.y + distance * 0.15,
    center.z + distance * 1.8,
  );

  camera.near = Math.max(maxDimension / 1000, 0.01);
  camera.far = Math.max(maxDimension * 100, 1000);
  camera.updateProjectionMatrix();
  controls.update();
}

function renderView(viewport, targetScene, targetCamera) {
  renderer.setViewport(viewport.left, viewport.bottom, viewport.width, viewport.height);
  renderer.setScissor(viewport.left, viewport.bottom, viewport.width, viewport.height);
  renderer.render(targetScene, targetCamera);
}

function render() {
  requestAnimationFrame(render);
  controls.update();

  const viewports = getViewports();

  renderer.setScissorTest(false);
  renderer.clear(true, true, true);
  renderer.setScissorTest(true);

  renderView(viewports.threeD, scene, camera);
  renderView(viewports.axial, sliceViews.axial.scene, sliceViews.axial.camera);
  renderView(viewports.coronal, sliceViews.coronal.scene, sliceViews.coronal.camera);
  renderView(viewports.sagittal, sliceViews.sagittal.scene, sliceViews.sagittal.camera);
}

window.addEventListener(
  'wheel',
  (event) => {
    const x = event.clientX;
    const y = event.clientY;
    const width = window.innerWidth;
    const height = window.innerHeight;

    const overThreeD = x < width / 2 && y < height / 2;
    if (overThreeD) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const direction = Math.sign(event.deltaY);
    if (direction === 0) return;

    for (const view of Object.values(sliceViews)) {
      const nextIndex = Math.max(
        0,
        Math.min(view.count - 1, view.index + direction),
      );
      if (nextIndex !== view.index) {
        loadSliceTexture(view, nextIndex);
      }
    }
  },
  { passive: false, capture: true },
);

function updateOrthographicCamera(view, viewportWidth, viewportHeight) {
  const aspect = viewportWidth / viewportHeight;
  const frustumSize = 1;
  view.camera.left = -frustumSize * aspect;
  view.camera.right = frustumSize * aspect;
  view.camera.top = frustumSize;
  view.camera.bottom = -frustumSize;
  view.camera.updateProjectionMatrix();
}

// Clean half-dimension viewport split matching CSS grid exactly
function getViewports() {
  const dpr = renderer.getPixelRatio();
  const totalWidth = window.innerWidth;
  const totalHeight = window.innerHeight - 48;

  const halfW = Math.floor(totalWidth / 2);
  const halfH = Math.floor(totalHeight / 2);

  // Leave a clean 4px gap/margin inside the quadrants to prevent bleeding
  const margin = Math.round(4 * dpr);

  const w = halfW - (margin * 2);
  const h = halfH - (margin * 2);

  return {
    threeD:   { left: margin,          bottom: halfH + margin, width: w, height: h },
    axial:    { left: halfW + margin,  bottom: halfH + margin, width: w, height: h },
    coronal:  { left: margin,          bottom: margin,         width: w, height: h },
    sagittal: { left: halfW + margin,  bottom: margin,         width: w, height: h },
  };
}

function onResize() {
  const width = window.innerWidth;
  const height = window.innerHeight - 48;

  renderer.setSize(width, height, false);

  const halfW = width / 2;
  const halfH = height / 2;

  camera.aspect = halfW / halfH;
  camera.updateProjectionMatrix();

  for (const view of Object.values(sliceViews)) {
    updateOrthographicCamera(view, halfW, halfH);
  }
}

window.addEventListener('resize', onResize);

render();

loadManifestAndModels().catch((error) => {
  console.error('Failed to initialize Forma:', error);
});