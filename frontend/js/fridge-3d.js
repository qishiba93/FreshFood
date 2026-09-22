/**
 * frontend/js/fridge-3d.js
 * 3D 智能微晶透视双门冰箱渲染引擎
 * 包含：
 * 1. 实体不透明侧壁与微晶通透玻璃门（关门透视阻隔，开门拾取食材）
 * 2. 临期/过期内部警报灯闪烁系统 (红灯急闪 / 黄灯呼吸)
 * 3. 超大倍率特写放大 (支持滚轮无级缩放 + 上下左右平移滑动 + 温区层级一键对焦)
 * 4. 修复视角平移逻辑：按 < 视角左移看左侧，按 > 视角右移看右侧
 * 5. 显式渲染高精看板与鼠标悬停实时保质期 HUD 浮窗
 */

import * as THREE from 'three';
import { OrbitControls } from './vendor/three/OrbitControls.js';
import { RoundedBoxGeometry } from './vendor/three/RoundedBoxGeometry.js';

export function createFridge3D({ host, onDoorToggle, onFoodSelect, onUnavailable }) {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 80);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute('role', 'img');
  renderer.domElement.setAttribute('aria-label', '智能微晶透视双门冰箱');
  host.appendChild(renderer.domElement);

  // 鼠标悬停保质期信息气泡 (HUD Tooltip)
  const tooltip = document.createElement('div');
  tooltip.style.cssText = `
    position: absolute;
    pointer-events: none;
    z-index: 30;
    display: none;
    background: rgba(15, 23, 42, 0.92);
    color: #ffffff;
    border: 1px solid rgba(148, 163, 184, 0.35);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    padding: 9px 13px;
    border-radius: 14px;
    font-size: 11px;
    line-height: 1.45;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
    transform: translate(-50%, -125%);
    transition: opacity 0.12s ease;
    white-space: nowrap;
  `;
  host.style.position = 'relative';
  host.appendChild(tooltip);

  // 1. 轨道控制器优化：支持平移、缩放与视角控制
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = true;          // 允许鼠标右键/双指触控平移
  controls.enableZoom = true;         // 允许滚轮无级缩放
  controls.zoomSpeed = 1.1;
  controls.panSpeed = 0.9;
  controls.minPolarAngle = Math.PI / 4.2;
  controls.maxPolarAngle = Math.PI / 1.7;
  // 适度放宽水平视角范围，方便观察深处与左右死角
  controls.minAzimuthAngle = -1.65;
  controls.maxAzimuthAngle = 1.65;
  controls.rotateSpeed = 0.72;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
  renderer.domElement.style.touchAction = 'none';

  let disposed = false;
  let visible = true;
  let frame = 0;

  const MIN_ZOOM = 0.18;
  const MAX_ZOOM = 1.45;
  let zoom = 1;
  let baseDistance = 10;
  let lastTime = 0;
  let inventoryRevision = 0;

  let targetCameraPos = null;
  let targetControlsTarget = null;
  let isTransitioning = false;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const resources = new Set();
  const inventoryResources = new Set();
  const listeners = new AbortController();
  const states = { upper: false, lower: false };
  const doors = {};
  const breathingLights = [];
  const breathingMaterials = [];
  const expiryAlerts = [];
  const model = new THREE.Group();
  const foods = new THREE.Group();
  scene.add(model);
  model.add(foods);

  function material(color, options = {}) {
    const value = new THREE.MeshStandardMaterial({ color, roughness: 0.35, ...options });
    resources.add(value);
    return value;
  }

  function box(parent, size, position, mat, radius = 0.02) {
    const geometry = radius
      ? new RoundedBoxGeometry(...size, 3, Math.min(radius, ...size.map(n => n / 2)))
      : new THREE.BoxGeometry(...size);
    resources.add(geometry);
    const mesh = new THREE.Mesh(geometry, mat);
    mesh.position.set(...position);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }

  function label(parent, text, width, height, position, options = {}) {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = Math.max(64, Math.round(512 * height / width));
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = options.background || 'rgba(24, 45, 48, 0.85)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = options.color || '#a7f3d0';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = `600 ${options.fontSize || 58}px "Segoe UI", "Microsoft YaHei", sans-serif`;
    ctx.fillText(text, 256, canvas.height / 2, 480);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    resources.add(texture);
    const mat = new THREE.MeshBasicMaterial({ map: texture, transparent: true, opacity: options.opacity || 0.9, toneMapped: false });
    resources.add(mat);
    const geometry = new THREE.PlaneGeometry(width, height);
    resources.add(geometry);
    const mesh = new THREE.Mesh(geometry, mat);
    mesh.position.set(...position);
    parent.add(mesh);
    return mesh;
  }

  // 冰箱材质
  const frameEnamel = material(0xa0bcba, { metalness: 0.45, roughness: 0.25 });
  const liner = material(0xf1f7f5, { roughness: 0.35 });
  const gasket = material(0x2d4346, { roughness: 0.7 });
  const sideFrame = material(0x95adb1, { metalness: 0.45, roughness: 0.3 });
  const sideLiner = material(0xf1f7f5, { roughness: 0.35 });
  const steel = material(0xd1dce0, { metalness: 0.85, roughness: 0.18 });
  const shelf = material(0x99d5d8, { transparent: true, opacity: 0.65, roughness: 0.1, metalness: 0.1 });
  const bin = material(0xbae6e8, { transparent: true, opacity: 0.45, roughness: 0.15, depthWrite: false });
  const ledGlow = material(0xecfeff, { emissive: 0xa5f3fc, emissiveIntensity: 2.2 });
  breathingMaterials.push(ledGlow);

  // 通透微晶玻璃材质
  const crystalGlassDoor = new THREE.MeshPhysicalMaterial({
    color: 0xf0fdfa,
    transparent: true,
    opacity: 0.24,
    roughness: 0.05,
    metalness: 0.08,
    reflectivity: 0.55,
    clearcoat: 0.92,
    clearcoatRoughness: 0.06,
    transmission: 0.86,
    ior: 1.52,
    depthWrite: false
  });
  resources.add(crystalGlassDoor);

  // 灯光系统
  scene.add(new THREE.HemisphereLight(0xffffff, 0x5a7d7d, 2.5));

  const keyLight = new THREE.DirectionalLight(0xfffaed, 3.8);
  keyLight.position.set(-3, 8, 6);
  keyLight.castShadow = true;
  keyLight.shadow.mapSize.set(1024, 1024);
  Object.assign(keyLight.shadow.camera, { left: -4, right: 4, top: 6, bottom: -4, near: 0.1, far: 20 });
  keyLight.shadow.bias = -0.0008;
  keyLight.shadow.radius = 3;
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0xcfefff, 2.2);
  fillLight.position.set(5, 4, 2);
  scene.add(fillLight);

  const interiorLightUpper = new THREE.PointLight(0xe0f7fa, 3.2, 3.8, 1.2);
  interiorLightUpper.position.set(0, 3.4, 0.2);
  scene.add(interiorLightUpper);

  const interiorLightLower = new THREE.PointLight(0xe0e7ff, 2.5, 3.0, 1.2);
  interiorLightLower.position.set(0, 1.2, 0.2);
  scene.add(interiorLightLower);
  breathingLights.push(
    { light: interiorLightUpper, base: 2.5, amplitude: 1.2 },
    { light: interiorLightLower, base: 2.0, amplitude: 1.0 }
  );

  const shadowMaterial = new THREE.ShadowMaterial({ color: 0x1f3b42, opacity: 0.08 });
  resources.add(shadowMaterial);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(100, 100), shadowMaterial);
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // 冰箱主体造型
  box(model, [2.26, 4.46, 0.15], [0, 2.47, -0.72], frameEnamel, 0.06);
  for (const x of [-1.06, 1.06]) {
    box(model, [0.16, 4.46, 1.58], [x, 2.47, 0.03], sideFrame, 0.05);
    box(model, [0.025, 4.13, 1.39], [x * 0.917, 2.46, 0.04], sideLiner, 0.01);
  }
  for (const y of [0.32, 4.62]) box(model, [2.13, 0.16, 1.58], [0, y, 0.03], frameEnamel, 0.05);
  box(model, [1.96, 4.12, 0.035], [0, 2.47, -0.625], liner, 0.012);
  box(model, [2.02, 0.12, 1.45], [0, 2.05, 0.07], liner);
  box(model, [2.12, 0.085, 0.085], [0, 2.05, 0.84], gasket, 0.01);

  for (const x of [-0.84, 0.84]) {
    for (const z of [-0.45, 0.55]) box(model, [0.2, 0.25, 0.25], [x, 0.15, z], gasket, 0.035);
  }

  for (const y of [0.5, 1.2, 2.22, 3.02, 3.82]) {
    box(model, [1.92, 0.04, 1.3], [0, y, 0.08], shelf, 0.012);
    box(model, [1.95, 0.04, 0.04], [0, y, 0.74], steel, 0.01);
  }
  for (const y of [0.52, 1.22]) {
    box(model, [1.87, 0.34, 0.035], [0, y + 0.15, 0.71], bin, 0.012);
    box(model, [0.45, 0.035, 0.045], [0, y + 0.23, 0.745], steel, 0.012);
  }

  for (const x of [-0.92, 0.92]) {
    box(model, [0.03, 2.15, 0.03], [x, 3.35, -0.47], ledGlow, 0.01);
    const stripLight = new THREE.PointLight(0xa5f3fc, 0.9, 2.2, 1.6);
    stripLight.position.set(x, 3.35, -0.34);
    scene.add(stripLight);
    breathingLights.push({ light: stripLight, base: 0.7, amplitude: 0.55 });
  }

  // 门板构造
  function buildTransparentDoor(zone, centerY, height, tempText) {
    const hinge = new THREE.Group();
    hinge.position.set(-1.11, centerY, 0.86);
    hinge.userData.zone = zone;
    model.add(hinge);

    const doorW = 2.22;
    const halfH = height / 2;

    box(hinge, [doorW, 0.07, 0.12], [1.11, halfH - 0.035, 0.04], frameEnamel, 0.02);
    box(hinge, [doorW, 0.07, 0.12], [1.11, -halfH + 0.035, 0.04], frameEnamel, 0.02);
    box(hinge, [0.07, height, 0.12], [0.035, 0, 0.04], frameEnamel, 0.02);
    box(hinge, [0.07, height, 0.12], [doorW - 0.035, 0, 0.04], frameEnamel, 0.02);

    const glassMesh = box(hinge, [doorW - 0.12, height - 0.12, 0.04], [1.11, 0, 0.04], crystalGlassDoor, 0.01);
    glassMesh.userData.zone = zone;

    const gasketThickness = 0.035;
    box(hinge, [doorW - 0.1, gasketThickness, 0.03], [1.11, halfH - 0.075, -0.04], gasket, 0.008);
    box(hinge, [doorW - 0.1, gasketThickness, 0.03], [1.11, -halfH + 0.075, -0.04], gasket, 0.008);
    box(hinge, [gasketThickness, height - 0.1, 0.03], [0.075, 0, -0.04], gasket, 0.008);
    box(hinge, [gasketThickness, height - 0.1, 0.03], [doorW - 0.075, 0, -0.04], gasket, 0.008);

    const handleY = zone === 'upper' ? -0.52 : 0.38;
    for (const y of [handleY - 0.24, handleY + 0.24]) {
      box(hinge, [0.065, 0.055, 0.14], [1.98, y, 0.14], steel, 0.02);
    }
    box(hinge, [0.075, 0.62, 0.075], [1.98, handleY, 0.23], steel, 0.03);

    label(hinge, tempText, 0.62, 0.26, [1.11, zone === 'upper' ? 0.35 : 0.28, 0.08], {
      background: 'rgba(15, 30, 35, 0.65)',
      color: '#6ee7b7',
      fontSize: 54
    });

    if (zone === 'upper') {
      label(hinge, 'FRESHPLATE · OS', 0.85, 0.11, [1.11, 0.88, 0.08], {
        background: 'rgba(255, 255, 255, 0.45)',
        color: '#134e4a',
        fontSize: 42
      });
    }

    doors[zone] = hinge;
  }

  buildTransparentDoor('upper', 3.355, 2.48, '4.0 °C');
  buildTransparentDoor('lower', 1.175, 1.76, '−18.0 °C');

  function formatExactExpiry(item) {
    if (item.is_expired) return '已过期 (严禁食用)';
    if (!item.expire_at) return '保质期未设定';
    const raw = String(item.expire_at).trim();
    if (raw.length >= 16) return raw.slice(0, 16);
    return raw;
  }

  function getStatusInfo(item) {
    const exactDate = formatExactExpiry(item);
    if (item.is_expired) {
      return { text: '已过期', bg: '#dc2626', badgeText: '严禁食用', colorHex: 0xdc2626, alertMode: 'red_blink', exactDate };
    }
    if (item.hours_left < 24) {
      return { text: '急需消耗', bg: '#ef4444', badgeText: '<24H', colorHex: 0xef4444, alertMode: 'red_blink', exactDate };
    }
    if (item.hours_left <= 48) {
      return { text: '尽快食用', bg: '#f59e0b', badgeText: '1~2天', colorHex: 0xf59e0b, alertMode: 'yellow_breathe', exactDate };
    }
    return { text: '保质充足', bg: '#10b981', badgeText: '新鲜', colorHex: 0x10b981, alertMode: 'none', exactDate };
  }

  function getExpiryCountdown(item) {
    if (item.is_expired) return '已超期失效';
    const hours = Number(item.hours_left);
    if (!Number.isFinite(hours)) return '保质未知';
    if (hours < 24) return `仅剩 ${Math.max(1, Math.round(hours))} 小时`;
    return `剩余 ${Math.max(1, Math.round(hours / 24))} 天`;
  }

  function clearItems() {
    inventoryRevision++;
    expiryAlerts.forEach(alert => {
      if (alert.pointLight) {
        scene.remove(alert.pointLight);
        alert.pointLight.dispose?.();
      }
    });
    expiryAlerts.length = 0;

    foods.clear();
    breathingMaterials.splice(1);
    inventoryResources.forEach(resource => resource.dispose());
    inventoryResources.clear();
    tooltip.style.display = 'none';
  }

  function createHighResStatusBillboard(item) {
    const status = getStatusInfo(item);
    const canvas = document.createElement('canvas');
    canvas.width = 1024;
    canvas.height = 240;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    if (typeof ctx.roundRect === 'function') {
      ctx.beginPath();
      ctx.roundRect(8, 8, 1008, 224, 36);
      ctx.fill();
    } else {
      ctx.fillRect(8, 8, 1008, 224);
    }

    ctx.fillStyle = status.bg;
    if (typeof ctx.roundRect === 'function') {
      ctx.beginPath();
      ctx.roundRect(14, 14, 250, 72, 20);
      ctx.fill();
    } else {
      ctx.fillRect(14, 14, 250, 72);
    }
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 36px "Segoe UI", "Microsoft YaHei", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${status.text}`, 139, 50);

    ctx.fillStyle = '#f1f5f9';
    ctx.textAlign = 'left';
    ctx.font = 'bold 40px "Segoe UI", "Microsoft YaHei", sans-serif';
    ctx.fillText(getExpiryCountdown(item), 284, 50);

    ctx.fillStyle = item.is_expired ? '#fca5a5' : '#a7f3d0';
    ctx.font = 'bold 44px "Segoe UI", "Microsoft YaHei", monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`保质至: ${status.exactDate}`, 512, 160);

    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
    inventoryResources.add(texture);

    const tagMaterial = new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      depthWrite: false,
      toneMapped: false
    });
    inventoryResources.add(tagMaterial);

    // 缩减至 0.48 宽度，避免邻近食物相互遮挡
    const tagGeometry = new THREE.PlaneGeometry(0.48, 0.12);
    inventoryResources.add(tagGeometry);
    const mesh = new THREE.Mesh(tagGeometry, tagMaterial);
    mesh.rotation.x = -0.18;
    return mesh;
  }

  function createFoodTextureCanvas(item, photoImage = null) {
    const status = getStatusInfo(item);
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    if (photoImage) {
      const aspect = photoImage.width / photoImage.height;
      let sw, sh, sx, sy;
      if (aspect > 1) {
        sh = photoImage.height; sw = photoImage.height;
        sx = (photoImage.width - sw) / 2; sy = 0;
      } else {
        sw = photoImage.width; sh = photoImage.width;
        sx = 0; sy = (photoImage.height - sh) / 2;
      }
      ctx.drawImage(photoImage, sx, sy, sw, sh, 0, 0, 512, 512);

      const grad = ctx.createLinearGradient(0, 240, 0, 512);
      grad.addColorStop(0, 'rgba(0,0,0,0)');
      grad.addColorStop(1, 'rgba(15,23,42,0.85)');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 240, 512, 272);
    } else {
      ctx.fillStyle = '#f8fafc';
      ctx.fillRect(0, 0, 512, 512);
      ctx.fillStyle = '#1e293b';
      ctx.font = 'bold 54px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(item.name, 256, 230, 460);
    }

    ctx.fillStyle = status.bg;
    ctx.fillRect(0, 0, 512, 80);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 36px "Microsoft YaHei", sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`● ${status.text}`, 24, 52);

    ctx.textAlign = 'right';
    ctx.font = 'bold 32px "Microsoft YaHei", sans-serif';
    ctx.fillText(status.badgeText, 488, 52);

    if (photoImage) {
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.font = 'bold 48px "Microsoft YaHei", sans-serif';
      ctx.shadowColor = 'rgba(0, 0, 0, 0.9)';
      ctx.shadowBlur = 8;
      ctx.fillText(item.name, 256, 350, 460);

      ctx.font = '34px "Microsoft YaHei", sans-serif';
      ctx.fillText(`${item.remaining_weight} ${item.unit}`, 256, 400, 460);
      ctx.shadowBlur = 0;
    } else {
      ctx.fillStyle = '#475569';
      ctx.font = '38px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`${item.remaining_weight} ${item.unit}`, 256, 310, 460);
    }

    ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
    ctx.fillRect(0, 432, 512, 80);

    ctx.fillStyle = item.is_expired ? '#f87171' : '#34d399';
    ctx.font = 'bold 28px "Segoe UI", monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`截止: ${status.exactDate}`, 256, 482, 480);

    return canvas;
  }

  function setItems(items) {
    if (disposed) return;
    clearItems();
    const revision = inventoryRevision;
    const loader = new THREE.TextureLoader();

    for (const [zone, location] of [['upper', 'refrigeration'], ['lower', 'freezer']]) {
      const zoneItems = items.filter(item => (item.location === 'refrigeration' ? 'refrigeration' : 'freezer') === location);

      zoneItems.slice(0, zone === 'upper' ? 9 : 6).forEach((item, index) => {
        const row = Math.floor(index / 3);
        const x = (index % 3 - 1) * 0.61;
        const y = (zone === 'upper' ? 2.245 + row * 0.8 : 0.545 + row * 0.7) + 0.24;
        const status = getStatusInfo(item);

        const initialCanvas = createFoodTextureCanvas(item, null);
        const texture = new THREE.CanvasTexture(initialCanvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        inventoryResources.add(texture);

        const frontMat = new THREE.MeshStandardMaterial({
          map: texture,
          roughness: 0.35,
          metalness: 0.1
        });
        const boxMat = new THREE.MeshStandardMaterial({
          color: 0xf1f5f9,
          roughness: 0.5
        });

        const geometry = new RoundedBoxGeometry(0.56, 0.56, 0.38, 3, 0.025);
        [frontMat, boxMat, geometry].forEach(r => inventoryResources.add(r));

        const foodMesh = new THREE.Mesh(geometry, [boxMat, boxMat, boxMat, boxMat, frontMat, boxMat]);
        foodMesh.position.set(x, y, 0.39);
        foodMesh.castShadow = true;
        foodMesh.receiveShadow = true;
        foodMesh.userData.item = item;
        foodMesh.userData.zone = zone;
        foods.add(foodMesh);

        const statusTag = createHighResStatusBillboard(item);
        statusTag.position.set(0, 0.34, 0.22);
        foodMesh.add(statusTag);

        const baseGeom = new THREE.CylinderGeometry(0.26, 0.28, 0.025, 16);
        const baseMat = new THREE.MeshStandardMaterial({
          color: status.colorHex,
          emissive: status.colorHex,
          emissiveIntensity: 0.4,
          roughness: 0.3
        });
        [baseGeom, baseMat].forEach(r => inventoryResources.add(r));
        const baseMesh = new THREE.Mesh(baseGeom, baseMat);
        baseMesh.position.set(0, -0.3, 0);
        foodMesh.add(baseMesh);

        if (status.alertMode === 'red_blink' || status.alertMode === 'yellow_breathe') {
          const beaconGeom = new THREE.SphereGeometry(0.045, 12, 12);
          const beaconMat = new THREE.MeshStandardMaterial({
            color: status.colorHex,
            emissive: status.colorHex,
            emissiveIntensity: 1.5,
            roughness: 0.2
          });
          [beaconGeom, beaconMat].forEach(r => inventoryResources.add(r));
          const beaconMesh = new THREE.Mesh(beaconGeom, beaconMat);
          beaconMesh.position.set(0, 0.32, 0.2);
          foodMesh.add(beaconMesh);

          const pointLight = new THREE.PointLight(status.colorHex, 1.6, 1.8, 1.4);
          pointLight.position.set(x, y + 0.28, 0.46);
          scene.add(pointLight);

          expiryAlerts.push({
            mode: status.alertMode,
            pointLight: pointLight,
            beaconMat: beaconMat,
            baseMat: baseMat,
            baseColor: status.colorHex
          });
        }

        if (item.image_url) {
          loader.load(item.image_url, (loadedImg) => {
            if (disposed || revision !== inventoryRevision) {
              loadedImg.dispose();
              return;
            }
            const compositeCanvas = createFoodTextureCanvas(item, loadedImg.image);
            const compositeTexture = new THREE.CanvasTexture(compositeCanvas);
            compositeTexture.colorSpace = THREE.SRGBColorSpace;
            inventoryResources.add(compositeTexture);

            frontMat.map = compositeTexture;
            frontMat.needsUpdate = true;
            loadedImg.dispose();
            invalidate();
          }, undefined, () => {});
        }
      });
    }
    invalidate();
  }

  function updateZoomButtons() {
    const btnIn = document.getElementById('fridgeZoomIn');
    const btnOut = document.getElementById('fridgeZoomOut');
    if (btnIn) btnIn.disabled = zoom <= (MIN_ZOOM + 0.01);
    if (btnOut) btnOut.disabled = zoom >= (MAX_ZOOM - 0.01);
  }

  function fit(reset = false) {
    if (disposed) return;
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();

    baseDistance = Math.max(6.3 / (2 * Math.tan(THREE.MathUtils.degToRad(17.5))), 6.8 / (2 * Math.tan(THREE.MathUtils.degToRad(17.5)) * camera.aspect));
    controls.minDistance = baseDistance * MIN_ZOOM;
    controls.maxDistance = baseDistance * MAX_ZOOM;

    if (reset) {
      controls.target.set(0, 2.35, 0.28);
      const direction = new THREE.Vector3(0.38, 0.16, 1).normalize();
      camera.position.copy(controls.target).addScaledVector(direction, baseDistance * zoom);
    }
    controls.update();
    invalidate();
  }

  function resetView() {
    isTransitioning = false;
    zoom = 1;
    controls.target.set(0, 2.35, 0.28);
    fit(true);
    updateZoomButtons();
  }

  function changeZoom(delta) {
    zoom = THREE.MathUtils.clamp(Number((zoom + delta).toFixed(2)), MIN_ZOOM, MAX_ZOOM);
    const direction = camera.position.clone().sub(controls.target).normalize();
    camera.position.copy(controls.target).addScaledVector(direction, baseDistance * zoom);
    controls.update();
    updateZoomButtons();
    invalidate();
  }

  function focusLevel(level) {
    let targetY = 2.35;
    if (level === 'top') {
      targetY = 3.35;
    } else if (level === 'bottom') {
      targetY = 1.15;
    } else {
      targetY = 2.35;
    }

    const deltaY = targetY - controls.target.y;
    targetControlsTarget = new THREE.Vector3(0, targetY, 0.28);
    targetCameraPos = camera.position.clone();
    targetCameraPos.y += deltaY;
    targetCameraPos.x = 0; // 自动复位 X 水平居中
    isTransitioning = true;
    invalidate();
  }

  function panVertical(deltaY) {
    isTransitioning = false;
    const clampedY = THREE.MathUtils.clamp(controls.target.y + deltaY, 0.85, 3.65);
    const actualDelta = clampedY - controls.target.y;
    controls.target.y = clampedY;
    camera.position.y += actualDelta;
    controls.update();
    invalidate();
  }

  // 【修复 16】：符合直觉的视角水平平移
  // 传负值（如 -0.25）向左看，传正值（如 +0.25）向右看
  function panHorizontal(deltaX) {
    isTransitioning = false;
    const clampedX = THREE.MathUtils.clamp(controls.target.x + deltaX, -0.75, 0.75);
    const actualDelta = clampedX - controls.target.x;
    controls.target.x = clampedX;
    camera.position.x += actualDelta;
    controls.update();
    invalidate();
  }

  // 约束平移边界（X/Y 双向锁紧，放大后自由滑动但不漂移出框）
  controls.addEventListener('change', () => {
    if (controls.target.y < 0.85) {
      const diff = 0.85 - controls.target.y;
      controls.target.y = 0.85;
      camera.position.y += diff;
    } else if (controls.target.y > 3.65) {
      const diff = 3.65 - controls.target.y;
      controls.target.y = 3.65;
      camera.position.y += diff;
    }

    if (controls.target.x < -0.75) {
      const diff = -0.75 - controls.target.x;
      controls.target.x = -0.75;
      camera.position.x += diff;
    } else if (controls.target.x > 0.75) {
      const diff = 0.75 - controls.target.x;
      controls.target.x = 0.75;
      camera.position.x += diff;
    }
  });

  function setDoors(next) {
    Object.assign(states, next);
    renderer.domElement.setAttribute('aria-label', `双门冰箱，冷藏门${states.upper ? '开启' : '关闭'}，冷冻门${states.lower ? '开启' : '关闭'}`);
    invalidate();
  }

  function draw(time) {
    frame = 0;
    if (disposed || !visible || document.hidden) return;
    const dt = Math.min((time - lastTime) / 1000 || 0.016, 0.05);
    lastTime = time;
    let moving = false;

    // 平滑运镜阻尼过渡
    if (isTransitioning && targetCameraPos && targetControlsTarget) {
      const tFactor = Math.min(1, dt * 7.5);
      camera.position.lerp(targetCameraPos, tFactor);
      controls.target.lerp(targetControlsTarget, tFactor);
      moving = true;

      if (camera.position.distanceTo(targetCameraPos) < 0.005 && controls.target.distanceTo(targetControlsTarget) < 0.005) {
        camera.position.copy(targetCameraPos);
        controls.target.copy(targetControlsTarget);
        isTransitioning = false;
      }
    }

    if (!reducedMotion.matches) {
      const pulse = 0.5 + 0.5 * Math.sin(time * 0.0032);
      ledGlow.emissiveIntensity = 1.7 + pulse * 2.2;
      breathingLights.forEach(({ light, base, amplitude }) => {
        light.intensity = base + pulse * amplitude;
      });

      const redFlashWave = Math.sin(time * 0.014);
      const isRedBright = redFlashWave > 0.0;
      const yellowBreatheWave = 0.5 + 0.5 * Math.sin(time * 0.005);

      expiryAlerts.forEach(alert => {
        if (alert.mode === 'red_blink') {
          const intensity = isRedBright ? 2.8 : 0.2;
          alert.pointLight.intensity = intensity;
          alert.beaconMat.emissiveIntensity = isRedBright ? 3.2 : 0.3;
          alert.baseMat.emissiveIntensity = isRedBright ? 1.4 : 0.2;
        } else if (alert.mode === 'yellow_breathe') {
          const intensity = 0.4 + yellowBreatheWave * 2.0;
          alert.pointLight.intensity = intensity;
          alert.beaconMat.emissiveIntensity = 0.6 + yellowBreatheWave * 2.2;
          alert.baseMat.emissiveIntensity = 0.3 + yellowBreatheWave * 1.0;
        }
      });
    }

    for (const zone of ['upper', 'lower']) {
      const target = states[zone] ? -1.95 : 0;
      const current = doors[zone].rotation.y;
      doors[zone].rotation.y = reducedMotion.matches ? target : THREE.MathUtils.damp(current, target, 8, dt);
      if (Math.abs(doors[zone].rotation.y - target) < 0.001) doors[zone].rotation.y = target;
      else moving = true;
    }

    const orbitChanged = controls.update();
    if (orbitChanged) {
      const currentDist = camera.position.distanceTo(controls.target);
      zoom = THREE.MathUtils.clamp(Number((currentDist / baseDistance).toFixed(2)), MIN_ZOOM, MAX_ZOOM);
      updateZoomButtons();
    }

    renderer.render(scene, camera);
    if (moving || orbitChanged || !reducedMotion.matches || expiryAlerts.length > 0 || isTransitioning) invalidate();
  }

  function invalidate() {
    if (!disposed && !frame && visible && !document.hidden) frame = requestAnimationFrame(draw);
  }
  controls.addEventListener('change', invalidate);

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let down = null;

  function getHitObject(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);

    const hits = raycaster.intersectObjects([foods, model], true).filter(hit => {
      return hit.object.material !== bin && hit.object.material !== shelf;
    });
    return hits;
  }

  function pick(event) {
    const hits = getHitObject(event);
    if (!hits.length) return null;

    const foodHit = hits.find(h => {
      let obj = h.object;
      while (obj && obj !== scene) {
        if (obj.userData && obj.userData.item) return true;
        obj = obj.parent;
      }
      return false;
    });

    if (foodHit) {
      let obj = foodHit.object;
      while (obj && obj !== scene) {
        if (obj.userData && obj.userData.item) {
          const zone = obj.userData.zone;
          if (!states[zone]) {
            return { zone };
          }
          return obj.userData;
        }
        obj = obj.parent;
      }
    }

    for (const hit of hits) {
      let obj = hit.object;
      while (obj && obj !== model) {
        if (obj.userData && obj.userData.zone) return obj.userData;
        obj = obj.parent;
      }
    }
    return null;
  }

  renderer.domElement.addEventListener('pointermove', event => {
    const rect = renderer.domElement.getBoundingClientRect();
    const hits = getHitObject(event);
    const foodHit = hits.find(h => {
      let obj = h.object;
      while (obj && obj !== scene) {
        if (obj.userData && obj.userData.item) return true;
        obj = obj.parent;
      }
      return false;
    });

    if (foodHit) {
      let obj = foodHit.object;
      while (obj && obj !== scene) {
        if (obj.userData && obj.userData.item) {
          const item = obj.userData.item;
          const status = getStatusInfo(item);
          const zone = obj.userData.zone;
          const isDoorClosed = !states[zone];

          tooltip.style.display = 'block';
          tooltip.style.left = `${event.clientX - rect.left}px`;
          tooltip.style.top = `${event.clientY - rect.top}px`;
          tooltip.innerHTML = `
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
              <strong style="font-size:13px;color:#f8fafc;">${item.name}</strong>
              <span style="font-size:9px;padding:2px 6px;border-radius:6px;background:${status.bg};color:#fff;font-weight:bold;">${status.text}</span>
            </div>
            <div style="color:${item.is_expired ? '#f87171' : '#34d399'};font-family:monospace;font-weight:bold;margin-bottom:2px;">
              📅 保质至: ${status.exactDate}
            </div>
            <div style="color:#94a3b8;font-size:10px;">
              ⏳ 倒计时: <strong style="color:#e2e8f0;">${getExpiryCountdown(item)}</strong> · 剩余: <strong>${item.remaining_weight}${item.unit}</strong>
            </div>
            ${isDoorClosed ? '<div style="color:#38bdf8;font-size:9px;margin-top:3px;border-top:1px solid rgba(255,255,255,0.1);padding-top:2px;">👉 点击玻璃将自动开启冰箱门</div>' : ''}
          `;
          return;
        }
        obj = obj.parent;
      }
    }
    tooltip.style.display = 'none';
  }, { signal: listeners.signal });

  renderer.domElement.addEventListener('pointerleave', () => {
    tooltip.style.display = 'none';
  }, { signal: listeners.signal });

  renderer.domElement.addEventListener('pointerdown', event => {
    if (event.isPrimary && event.button === 0) down = { x: event.clientX, y: event.clientY, id: event.pointerId };
    else down = null;
  }, { signal: listeners.signal });

  renderer.domElement.addEventListener('pointerup', event => {
    if (!down || down.id !== event.pointerId) return;
    const distance = Math.hypot(event.clientX - down.x, event.clientY - down.y);
    down = null;
    if (distance > 6) return;
    const hit = pick(event);
    if (hit?.item) onFoodSelect(hit.item);
    else if (hit?.zone) onDoorToggle(hit.zone);
  }, { signal: listeners.signal });

  renderer.domElement.addEventListener('pointercancel', () => { down = null; }, { signal: listeners.signal });
  renderer.domElement.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    dispose();
    onUnavailable();
  }, { signal: listeners.signal });

  // 绑定控制面板按键
  document.getElementById('fridgeResetView')?.addEventListener('click', resetView, { signal: listeners.signal });
  document.getElementById('fridgeZoomIn')?.addEventListener('click', () => changeZoom(-0.15), { signal: listeners.signal });
  document.getElementById('fridgeZoomOut')?.addEventListener('click', () => changeZoom(0.15), { signal: listeners.signal });

  // 温区快速对焦
  document.getElementById('fridgeFocusTop')?.addEventListener('click', () => focusLevel('top'), { signal: listeners.signal });
  document.getElementById('fridgeFocusMid')?.addEventListener('click', () => focusLevel('mid'), { signal: listeners.signal });
  document.getElementById('fridgeFocusBottom')?.addEventListener('click', () => focusLevel('bottom'), { signal: listeners.signal });

  // 视角平移
  document.getElementById('fridgePanUp')?.addEventListener('click', () => panVertical(0.35), { signal: listeners.signal });
  document.getElementById('fridgePanDown')?.addEventListener('click', () => panVertical(-0.35), { signal: listeners.signal });
  // 【修复 16】：点击 < 视角向左移（看左侧），点击 > 视角向右移（看右侧）
  document.getElementById('fridgePanLeft')?.addEventListener('click', () => panHorizontal(-0.25), { signal: listeners.signal });
  document.getElementById('fridgePanRight')?.addEventListener('click', () => panHorizontal(0.25), { signal: listeners.signal });

  document.addEventListener('visibilitychange', invalidate, { signal: listeners.signal });

  const resizeObserver = new ResizeObserver(() => fit());
  resizeObserver.observe(host);
  const intersectionObserver = new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    if (visible) invalidate();
  });
  intersectionObserver.observe(host);

  function dispose() {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(frame);
    listeners.abort();
    resizeObserver.disconnect();
    intersectionObserver.disconnect();
    controls.dispose();
    clearItems();
    resources.forEach(resource => resource.dispose());
    renderer.dispose();
    renderer.domElement.remove();
    tooltip.remove();
  }

  resetView();
  return { setDoors, setItems, dispose };
}