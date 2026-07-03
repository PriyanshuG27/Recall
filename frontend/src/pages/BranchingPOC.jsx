import React, { useRef, useMemo, useState, useEffect, useCallback } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

/* ═══ CONSTANTS ══════════════════════════════════════════════════════════ */
const G         = 62;
const FALL_H    = 9;
const FALL_MS   = Math.sqrt(2 * FALL_H / G) * 1000;
const GHOST_MS  = 240;
const SETTLE_MS = 420;
const GAP_MS    = 150;
const sr = (s) => { const x = Math.sin(s * 1.618 + 2.718) * 10000; return x - Math.floor(x); };

/* ═══ STAGES ═════════════════════════════════════════════════════════════ */
const STAGE_NAMES  = ['Hut', 'Cottage', 'House', 'Manor', 'Villa', 'Castle'];
const STAGE_SCORES = [0, 22, 46, 72, 90, 97];
const STAGE_SUBS   = [
  'First shelter. First warmth.',
  'Walls that hold the rain out.',
  'A place called home.',
  'Every room holds a memory.',
  'Concrete and glass. A new chapter.',
  'Built to last centuries.',
];
const getStage = (score) => STAGE_SCORES.reduce((a, t, i) => score >= t ? i : a, 0);

/* ═══ BUILDING SLOTS ═════════════════════════════════════════════════════
   comp: 'post' | 'wicker' | 'stone' | 'plaster' | 'brick' | 'chimney' | 'tower'
   si: stage index  sz: [w,h,d]  sc: min score
═══════════════════════════════════════════════════════════════════════ */
/*
  ALIGNMENT MATH — no gaps between layers:
  HUT posts/panels:  ground=0,  top = 0+1.84 = 1.84   (posts), panels y=0.92
  STONE corners:     ground=0,  center y=0.16, top=0.32
  PLASTER walls:     sit on stone top 0.32, h=0.56 → center y = 0.32+0.28 = 0.60, top=0.88
  BRICK 2nd floor:   sit on plaster top 0.88, h=0.52 → center y = 0.88+0.26 = 1.14, top=1.40
  CHIMNEY:           sits on brick top 1.40, h=0.80 → center y = 1.40+0.40 = 1.80
  TOWER blocks:      cumulative from ground
*/
const SLOTS = [
  // HUT — bamboo posts + wicker panels (si=0, sc 2–20)  retirable=true: fully replaced by cottage
  { id:0,  comp:'post',    si:0, retirable:true,  pos:[-1.02,0.92,-0.80], sz:[0.14,1.84,0.14], sc:2  },
  { id:1,  comp:'post',    si:0, retirable:true,  pos:[ 1.02,0.92,-0.80], sz:[0.14,1.84,0.14], sc:4  },
  { id:2,  comp:'post',    si:0, retirable:true,  pos:[-1.02,0.92, 0.80], sz:[0.14,1.84,0.14], sc:6  },
  { id:3,  comp:'post',    si:0, retirable:true,  pos:[ 1.02,0.92, 0.80], sz:[0.14,1.84,0.14], sc:8  },
  { id:4,  comp:'wicker',  si:0, retirable:true,  pos:[-1.03,0.82, 0.00], sz:[0.09,1.28,1.54], sc:10 },
  { id:5,  comp:'wicker',  si:0, retirable:true,  pos:[ 1.03,0.82, 0.00], sz:[0.09,1.28,1.54], sc:12 },
  { id:6,  comp:'wicker',  si:0, retirable:true,  pos:[ 0.00,0.82,-0.81], sz:[1.92,1.28,0.09], sc:15 },
  { id:7,  comp:'wicker',  si:0, retirable:true,  pos:[ 0.00,0.82, 0.81], sz:[1.92,1.28,0.09], sc:20, hasDoor:true },

  // COTTAGE — stone corners: FULL-HEIGHT piers (permanent) + plaster walls (si=1, sc 22–46)
  // Stone piers: sz[2]=0.76 = exact bridge between side wall front-face (z=0.99) and front/back wall (z=1.41)
  { id:8,  comp:'stone',   si:1, permanent:true,  pos:[-1.57,0.44,-1.37], sz:[0.54,0.88,0.76], sc:22 },
  { id:9,  comp:'stone',   si:1, permanent:true,  pos:[ 1.57,0.44,-1.37], sz:[0.54,0.88,0.76], sc:24 },
  { id:10, comp:'stone',   si:1, permanent:true,  pos:[-1.57,0.44, 1.37], sz:[0.54,0.88,0.76], sc:26 },
  { id:11, comp:'stone',   si:1, permanent:true,  pos:[ 1.57,0.44, 1.37], sz:[0.54,0.88,0.76], sc:28 },
  // Plaster: h=0.88 from ground → center y=0.44, top=0.88; front wall widens to match back
  { id:12, comp:'plaster', si:1, retirable:true,  pos:[-1.58,0.44, 0.00], sz:[0.34,0.88,1.98], sc:31 },
  { id:13, comp:'plaster', si:1, retirable:true,  pos:[ 1.58,0.44, 0.00], sz:[0.34,0.88,1.98], sc:34, hasWindow:true },
  { id:14, comp:'plaster', si:1, retirable:true,  pos:[ 0.00,0.44,-1.58], sz:[2.90,0.88,0.34], sc:37, hasWindow:true },
  { id:15, comp:'plaster', si:1, retirable:true,  pos:[ 0.00,0.44, 1.58], sz:[2.90,0.88,0.34], sc:42, hasDoor:true  },

  // HOUSE — full-height fired brick from ground (si=2, sc 48–65)
  // Brick: bottom=0, h=1.40 → center y=0.70, top=1.40  (covers entire wall face from ground)
  { id:16, comp:'brick',   si:2, retirable:true, pos:[-1.58,0.70, 0.00], sz:[0.34,1.40,1.98], sc:48, hasWindow:true },
  { id:17, comp:'brick',   si:2, retirable:true, pos:[ 1.58,0.70, 0.00], sz:[0.34,1.40,1.98], sc:52, hasWindow:true },
  { id:18, comp:'brick',   si:2, retirable:true, pos:[ 0.00,0.70,-1.58], sz:[2.50,1.40,0.34], sc:56 },
  { id:19, comp:'brick',   si:2, retirable:true, pos:[ 0.00,0.70, 1.58], sz:[2.50,1.40,0.34], sc:60, hasDoor:true },
  // Chimney: center y=1.80, h=0.80 → bottom=1.40 (flush on brick top), top=2.20
  { id:20, comp:'chimney', si:2, retirable:true, pos:[ 1.02,1.80, 0.00], sz:[0.28,0.80,0.28], sc:65 },

  // HOUSE CORNER EXTENSIONS — fill y=0.88→1.40 gap between stone quoins and brick wall tops
  // Drop at sc=47 (just before first brick at sc=48) — this also triggers retireStage(1)
  { id:29, comp:'stone',   si:2, retirable:true, pos:[-1.57,1.14,-1.37], sz:[0.54,0.52,0.76], sc:47 },
  { id:30, comp:'stone',   si:2, retirable:true, pos:[ 1.57,1.14,-1.37], sz:[0.54,0.52,0.76], sc:47 },
  { id:31, comp:'stone',   si:2, retirable:true, pos:[-1.57,1.14, 1.37], sz:[0.54,0.52,0.76], sc:47 },
  { id:32, comp:'stone',   si:2, retirable:true, pos:[ 1.57,1.14, 1.37], sz:[0.54,0.52,0.76], sc:47 },

  // MANOR — cream rendered plaster + mansard roof (si=3, sc:72–89)  [retirable → replaced by Villa]
  // Footprint: side walls x=±2.20, front/back z=±2.05
  // GF:  h=1.32, center y=0.66, top=1.32
  // 2F:  h=1.10, bottom=1.44, center y=1.99, top=2.54
  // Cornice belt: y=1.32→1.44 (h=0.12) | Parapet: h=0.26 at y=2.61
  { id:21, comp:'manor_wall',    si:3, retirable:true, pos:[-2.20,0.66, 0.00], sz:[0.28,1.32,4.10], sc:72, hasWindow:true },
  { id:22, comp:'manor_wall',    si:3, retirable:true, pos:[ 2.20,0.66, 0.00], sz:[0.28,1.32,4.10], sc:73, hasWindow:true },
  { id:23, comp:'manor_wall',    si:3, retirable:true, pos:[ 0.00,0.66,-2.05], sz:[4.12,1.32,0.28], sc:74 },
  { id:24, comp:'manor_wall',    si:3, retirable:true, pos:[ 0.00,0.66, 2.05], sz:[4.12,1.32,0.28], sc:75, hasDoor:true  },
  { id:25, comp:'manor_cornice', si:3, retirable:true, pos:[ 0.00,1.38, 0.00], sz:[4.68,0.12,4.68], sc:76 },
  { id:26, comp:'manor_porch',   si:3, retirable:true, pos:[ 0.00,0.66, 2.52], sz:[2.80,1.32,0.90], sc:77 },
  { id:27, comp:'manor_wall',    si:3, retirable:true, pos:[-2.20,1.99, 0.00], sz:[0.28,1.10,4.10], sc:78, hasWindow:true },
  { id:28, comp:'manor_wall',    si:3, retirable:true, pos:[ 2.20,1.99, 0.00], sz:[0.28,1.10,4.10], sc:79, hasWindow:true },
  { id:33, comp:'manor_wall',    si:3, retirable:true, pos:[ 0.00,1.99,-2.05], sz:[4.12,1.10,0.28], sc:80 },
  { id:34, comp:'manor_wall',    si:3, retirable:true, pos:[ 0.00,1.99, 2.05], sz:[4.12,1.10,0.28], sc:82, hasWindow:true },
  { id:35, comp:'manor_balcony', si:3, retirable:true, pos:[ 0.00,1.44, 2.74], sz:[3.40,0.08,1.00], sc:84 },
  { id:36, comp:'manor_parapet', si:3, retirable:true, pos:[ 0.00,2.61, 0.00], sz:[4.68,0.26,4.68], sc:86 },
  { id:37, comp:'manor_cornice', si:3, retirable:true, pos:[ 0.00,2.52, 0.00], sz:[4.78,0.08,4.78], sc:88 },
  // VILLA — modern white concrete, floor slabs, full-height glazing (si=4, sc:90–96)
  // Footprint: side walls x=±2.60, front/back z=±2.30
  // GF: h=1.20, center y=0.60, top=1.20 | Slab: h=0.12, center y=1.26
  // 2F: h=1.10, bottom=1.32, center y=1.87, top=2.42
  { id:42, comp:'modern_wall', si:4, pos:[-2.60,0.60, 0.00], sz:[0.24,1.20,4.60], sc:90, hasWindow:true },
  { id:43, comp:'modern_wall', si:4, pos:[ 2.60,0.60, 0.00], sz:[0.24,1.20,4.60], sc:91, hasWindow:true },
  { id:44, comp:'modern_wall', si:4, pos:[ 0.00,0.60,-2.30], sz:[4.96,1.20,0.24], sc:92 },
  { id:45, comp:'modern_wall', si:4, pos:[ 0.00,0.60, 2.30], sz:[4.96,1.20,0.24], sc:93, hasDoor:true },
  { id:46, comp:'modern_slab', si:4, pos:[ 0.00,1.26, 0.00], sz:[5.44,0.12,4.88], sc:94 },
  { id:47, comp:'modern_wall', si:4, pos:[-2.60,1.87, 0.00], sz:[0.24,1.10,4.60], sc:95, hasWindow:true },
  { id:48, comp:'modern_wall', si:4, pos:[ 2.60,1.87, 0.00], sz:[0.24,1.10,4.60], sc:95, hasWindow:true },
  { id:49, comp:'modern_wall', si:4, pos:[ 0.00,1.87,-2.30], sz:[4.96,1.10,0.24], sc:95 },
  { id:50, comp:'modern_wall', si:4, pos:[ 0.00,1.87, 2.30], sz:[4.96,1.10,0.24], sc:96, hasWindow:true },
  // CASTLE — stone towers flanking the Villa (si=5, sc:97–100)
  { id:38, comp:'tower',       si:5, pos:[-3.10,0.60,-2.60], sz:[1.20,1.20,0.82], sc:97 },
  { id:39, comp:'tower',       si:5, pos:[-3.10,1.90,-2.60], sz:[1.18,1.40,0.80], sc:98 },
  { id:40, comp:'tower',       si:5, pos:[ 3.10,0.60,-2.60], sz:[1.20,1.20,0.82], sc:99 },
  { id:41, comp:'tower',       si:5, pos:[ 3.10,1.90,-2.60], sz:[1.18,1.40,0.80], sc:100 },
];

const POC_SCORE   = 96; // 68=House · 89=Manor · 96=Villa · 100=Castle
const CRACKED_IDS = new Set([7, 14]);

/* ═══ ANIMATED BLOCK WRAPPER ════════════════════════════════════════════
   Handles ghost/fall/settle/crack/repair states. Children = placed visuals.
═══════════════════════════════════════════════════════════════════════ */
function AnimatedBlock({ slot, state, goldMatRef, children }) {
  const groupRef  = useRef();
  const prevState = useRef(state);
  const enterT    = useRef(0);

  const crackTiltX = useMemo(() => (sr(slot.id * 3.10) - 0.5) * 0.068, [slot.id]);
  const crackTiltZ = useMemo(() => (sr(slot.id * 5.77) - 0.5) * 0.068, [slot.id]);

  const crackGeo = useMemo(() => {
    const [W, H, D] = slot.sz;
    const z = Math.max(D, W) * 0.5 + 0.014;
    const pts = [
      new THREE.Vector3(-W * 0.22, -H * 0.30, z),
      new THREE.Vector3( W * 0.10,  0,         z),
      new THREE.Vector3(-W * 0.06,  H * 0.30,  z),
    ];
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 12, 0.009, 4, false);
  }, [slot.sz]);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    if (prevState.current !== state) {
      prevState.current = state;
      enterT.current = clock.elapsedTime;
      if (['placed','cracked','repaired'].includes(state)) {
        groupRef.current.position.set(...slot.pos);
        groupRef.current.rotation.set(
          state === 'cracked' ? crackTiltX : 0, 0,
          state === 'cracked' ? crackTiltZ : 0
        );
      }
    }
    const t = clock.elapsedTime - enterT.current;
    if (state === 'falling') {
      const y = Math.max(slot.pos[1], (slot.pos[1] + FALL_H) - 0.5 * G * t * t);
      groupRef.current.position.set(slot.pos[0], y, slot.pos[2]);
      groupRef.current.rotation.set(0, 0, 0);
    } else if (state === 'settling') {
      const w = Math.sin(t * 22) * 0.042 * Math.exp(-t * 11);
      groupRef.current.position.set(...slot.pos);
      groupRef.current.rotation.set(w, 0, w * 0.65);
    } else if (state === 'repairing' && goldMatRef?.current) {
      const p = Math.min(1, t / 2.4);
      goldMatRef.current.opacity           = p * 0.95;
      goldMatRef.current.emissiveIntensity = 2.4 - p * 1.7;
    }
  });

  if (state === 'pending') return null;

  const isGhost     = state === 'ghost';
  const isFalling   = state === 'falling';
  const isCracked   = ['cracked','repairing','repaired'].includes(state);
  const isRepairing = state === 'repairing';
  const isRepaired  = state === 'repaired';

  return (
    <group
      ref={groupRef}
      position={[slot.pos[0], isFalling ? slot.pos[1] + FALL_H : slot.pos[1], slot.pos[2]]}
      rotation={[isCracked ? crackTiltX : 0, 0, isCracked ? crackTiltZ : 0]}
    >
      {isGhost ? (
        <mesh>
          <boxGeometry args={slot.sz} />
          <meshBasicMaterial wireframe color="#88C8E8" opacity={0.28} transparent />
        </mesh>
      ) : (
        <>
          {children}
          {isCracked && (
            <mesh geometry={crackGeo}>
              <meshBasicMaterial color="#060402" />
            </mesh>
          )}
          {(isRepairing || isRepaired) && (
            <mesh geometry={crackGeo}>
              <meshStandardMaterial
                ref={goldMatRef}
                color="#D4AF37" emissive="#FFD700"
                emissiveIntensity={isRepaired ? 0.78 : 0}
                roughness={0.06} metalness={0.95}
                transparent opacity={isRepaired ? 0.95 : 0}
              />
            </mesh>
          )}
        </>
      )}
    </group>
  );
}

/* ═══ BLOCK VISUAL COMPONENTS ════════════════════════════════════════════ */

/* Bamboo post with node rings */
function PostVisual({ slot }) {
  const r = slot.sz[0] / 2;
  const h = slot.sz[1];
  const postGeo = useMemo(() => {
    const g = new THREE.CylinderGeometry(r * 0.78, r, h, 9, 6);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const y    = p.getY(i);
      const node = Math.sin(y * Math.PI * 5 / h + slot.id * 1.4) > 0.75 ? 0.012 : 0;
      const th   = Math.atan2(p.getZ(i), p.getX(i));
      const d    = Math.sqrt(p.getX(i) ** 2 + p.getZ(i) ** 2);
      p.setXYZ(i, Math.cos(th)*(d+node), y, Math.sin(th)*(d+node));
    }
    g.computeVertexNormals();
    return g;
  }, [r, h, slot.id]);

  const nodeGeo  = useMemo(() => new THREE.CylinderGeometry(r * 0.96, r * 0.96, 0.052, 9), [r]);
  const bambooHue = 0.09 + sr(slot.id) * 0.03;
  const postColor = new THREE.Color().setHSL(bambooHue, 0.62, 0.32);

  return (
    <>
      <mesh geometry={postGeo} castShadow receiveShadow>
        <meshStandardMaterial color={postColor} roughness={0.76} metalness={0.0} />
      </mesh>
      {[0.22, 0.50, 0.78].map((t, i) => (
        <mesh key={i} geometry={nodeGeo} position={[0, h*(t-0.5), 0]} castShadow>
          <meshStandardMaterial color="#4A2E0A" roughness={0.82} />
        </mesh>
      ))}
    </>
  );
}

/* Wicker/mud wall panel with horizontal ribs + optional door opening */
function WickerVisual({ slot }) {
  const [W, H, D] = slot.sz;
  // isXthin: side wall, thin in X, extends in Z → ribs run along Z, placed on ±X face
  // else:    front/back wall, thin in Z, extends in X → ribs run along X, placed on ±Z face
  const isXthin  = W < D;
  const thinHalf = (isXthin ? W : D) / 2;  // half of thin dimension
  const longDim  = isXthin ? D : W;          // long dimension (ribs span this)
  const DOOR_W   = longDim * 0.32;
  const DOOR_H   = H * 0.60;

  const wallGeo = useMemo(() => {
    const g = new THREE.BoxGeometry(W, H, D, 1, 2, 1);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const n = (sr(i * 7 + slot.id * 11) - 0.5) * 0.006;
      p.setXYZ(i, p.getX(i)+n, p.getY(i)+n, p.getZ(i)+n);
    }
    g.computeVertexNormals();
    return g;
  }, [W, H, D, slot.id]);

  const N_RIBS  = 11;
  const RIB_T   = 0.015; // rib thickness sticking out from the face

  // Rib geometry: extends along the LONG axis, thin on the other two
  const ribGeo = useMemo(() =>
    isXthin
      ? new THREE.BoxGeometry(RIB_T, H / N_RIBS * 0.40, longDim * 1.008) // side wall: rib along Z
      : new THREE.BoxGeometry(longDim * 1.008, H / N_RIBS * 0.40, RIB_T), // front/back: rib along X
  [isXthin, longDim, H]);

  const ribs = useMemo(() =>
    Array.from({ length: N_RIBS }, (_, i) => ({
      y:   -H/2 + (i + 0.5) * (H / N_RIBS),
      alt: i % 2 === 0,
    }))
  , [H]);

  // Dark bamboo trim top + bottom — spans the long axis
  const trimGeo = useMemo(() =>
    isXthin
      ? new THREE.BoxGeometry(0.062, 0.060, longDim * 1.01) // side wall: trim along Z
      : new THREE.BoxGeometry(longDim * 1.01, 0.060, 0.062), // front/back: trim along X
  [isXthin, longDim]);

  // Rib face offsets: placed on ±X face (side wall) or ±Z face (front/back)
  const faceOffset = thinHalf + RIB_T / 2;

  return (
    <>
      <mesh geometry={wallGeo} castShadow receiveShadow>
        <meshStandardMaterial color="#C49060" roughness={0.90} />
      </mesh>
      {ribs.map((r, i) => (
        <React.Fragment key={i}>
          <mesh geometry={ribGeo}
            position={isXthin ? [ faceOffset, r.y, 0] : [0, r.y,  faceOffset]}
            castShadow
          >
            <meshStandardMaterial color={r.alt ? '#A06830' : '#B8824A'} roughness={0.88} />
          </mesh>
          <mesh geometry={ribGeo}
            position={isXthin ? [-faceOffset, r.y, 0] : [0, r.y, -faceOffset]}
            castShadow
          >
            <meshStandardMaterial color={r.alt ? '#A06830' : '#B8824A'} roughness={0.88} />
          </mesh>
        </React.Fragment>
      ))}
      {[-1, 1].map((s, i) => (
        <mesh key={i} geometry={trimGeo} position={[0, s*(H/2), 0]} castShadow>
          <meshStandardMaterial color="#4A2E0A" roughness={0.78} />
        </mesh>
      ))}
      {/* Door opening — dark plane on outward face when hasDoor */}
      {slot.hasDoor && (
        <mesh
          position={isXthin
            ? [faceOffset + 0.003, -H * 0.20, 0]
            : [0, -H * 0.20, faceOffset + 0.003]}
        >
          <planeGeometry args={[DOOR_W, DOOR_H]} />
          <meshStandardMaterial color="#160C04" roughness={0.95} />
        </mesh>
      )}
    </>
  );
}

/* Rough stone block (foundation) */
function StoneVisual({ slot }) {
  const [W, H, D] = slot.sz;
  const geo = useMemo(() => {
    const g = new THREE.BoxGeometry(W, H, D, 4, 2, 4);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const n = (sr(i * 13.7 + slot.id * 5.3) - 0.5) * 0.038;
      p.setXYZ(i, p.getX(i)+n, p.getY(i)+n*0.5, p.getZ(i)+n);
    }
    g.computeVertexNormals();
    return g;
  }, [W, H, D, slot.id]);
  return (
    <mesh geometry={geo} castShadow receiveShadow>
      <meshStandardMaterial color="#C8B89A" roughness={0.93} metalness={0.02} />
    </mesh>
  );
}

/* Plaster wall with timber frame + optional window/door */
function PlasterVisual({ slot }) {
  const [W, H, D] = slot.sz;
  const isX = W < D; // thin in X = side wall

  const wallGeo = useMemo(() => {
    const g = new THREE.BoxGeometry(W, H, D, 2, 2, 1);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const n = (sr(i*11 + slot.id*7) - 0.5) * 0.010;
      p.setXYZ(i, p.getX(i)+n, p.getY(i)+n, p.getZ(i)+n);
    }
    g.computeVertexNormals();
    return g;
  }, [W, H, D, slot.id]);

  /* 4-pane cottage window */
  const WIN_W = 0.36, WIN_H = 0.40, FRAME = 0.052;
  const hasWindow = slot.hasWindow;
  const hasDoor   = slot.hasDoor;

  /* Door arch path */
  const DOOR_W = 0.42, DOOR_H = 0.62;
  const doorPath = useMemo(() => new THREE.CatmullRomCurve3([
    new THREE.Vector3(-DOOR_W/2, -DOOR_H/2, 0.01),
    new THREE.Vector3(-DOOR_W/2,  DOOR_H*0.20, 0.01),
    new THREE.Vector3( 0,          DOOR_H/2 + DOOR_W*0.28, 0.01),
    new THREE.Vector3( DOOR_W/2,  DOOR_H*0.20, 0.01),
    new THREE.Vector3( DOOR_W/2, -DOOR_H/2, 0.01),
  ], false), []);
  const doorFrameGeo = useMemo(() => new THREE.TubeGeometry(doorPath, 24, 0.042, 7, false), [doorPath]);

  /* Sign-aware facing: left/back walls face outward in their -X/-Z direction */
  const extSign = isX ? Math.sign(slot.pos[0]) : Math.sign(slot.pos[2]);
  const faceOffset = isX
    ? [extSign * (W/2 + 0.018), 0, 0]
    : [0, 0, extSign * (D/2 + 0.018)];
  const faceRot = isX
    ? [0, extSign > 0 ? Math.PI/2 : -Math.PI/2, 0]
    : [0, extSign > 0 ? 0 : Math.PI, 0];

  const TIMBER  = '#52341A';
  const PLASTER = '#D4C0A0';
  const FRAME_C = '#6A4228';

  return (
    <>
      {/* Plaster wall body */}
      <mesh geometry={wallGeo} castShadow receiveShadow>
        <meshStandardMaterial color={PLASTER} roughness={0.84} />
      </mesh>

      {/* Timber frame + window/door — on the EXTERIOR face */}
      <group position={faceOffset} rotation={faceRot}>
        {/* Top horizontal beam */}
        <mesh position={[0, H/2 - 0.030, 0]} castShadow>
          <boxGeometry args={[Math.max(W,D)+0.04, 0.062, 0.054]} />
          <meshStandardMaterial color={TIMBER} roughness={0.75} />
        </mesh>
        {/* Bottom horizontal beam */}
        <mesh position={[0, -H/2+0.030, 0]} castShadow>
          <boxGeometry args={[Math.max(W,D)+0.04, 0.062, 0.054]} />
          <meshStandardMaterial color={TIMBER} roughness={0.75} />
        </mesh>
        {/* Mid horizontal beam */}
        <mesh position={[0, 0, 0]} castShadow>
          <boxGeometry args={[Math.max(W,D)+0.02, 0.050, 0.045]} />
          <meshStandardMaterial color={TIMBER} roughness={0.75} />
        </mesh>
        {/* Left vertical beam */}
        <mesh position={[-Math.max(W,D)/2+0.030, 0, 0]} castShadow>
          <boxGeometry args={[0.062, H+0.04, 0.054]} />
          <meshStandardMaterial color={TIMBER} roughness={0.75} />
        </mesh>
        {/* Right vertical beam */}
        <mesh position={[Math.max(W,D)/2-0.030, 0, 0]} castShadow>
          <boxGeometry args={[0.062, H+0.04, 0.054]} />
          <meshStandardMaterial color={TIMBER} roughness={0.75} />
        </mesh>

        {/* 4-pane cottage window — centred on wall */}
        {hasWindow && (
          <group position={[0, H*0.06, 0]}>
            {/* Luminous amber glass */}
            <mesh position={[0, 0, 0.020]}>
              <planeGeometry args={[WIN_W, WIN_H]} />
              <meshStandardMaterial
                color="#FFD878"
                emissive="#FF9020"
                emissiveIntensity={2.2}
                roughness={0.15} metalness={0.2}
                transparent opacity={0.88}
              />
            </mesh>
            {/* Cross dividers */}
            <mesh position={[0, 0, 0.036]}><boxGeometry args={[WIN_W, 0.032, 0.052]} /><meshStandardMaterial color={FRAME_C} roughness={0.72} /></mesh>
            <mesh position={[0, 0, 0.036]}><boxGeometry args={[0.032, WIN_H, 0.052]} /><meshStandardMaterial color={FRAME_C} roughness={0.72} /></mesh>
            {/* Frame surround */}
            {[[0, WIN_H/2+FRAME/2], [0, -(WIN_H/2+FRAME/2)]].map(([fx,fy],i)=>(
              <mesh key={i} position={[fx,fy,0.040]} castShadow><boxGeometry args={[WIN_W+FRAME*2, FRAME, 0.060]} /><meshStandardMaterial color={FRAME_C} roughness={0.72} /></mesh>
            ))}
            {[[-(WIN_W/2+FRAME/2),0],[WIN_W/2+FRAME/2,0]].map(([fx,fy],i)=>(
              <mesh key={i} position={[fx,fy,0.040]} castShadow><boxGeometry args={[FRAME, WIN_H, 0.060]} /><meshStandardMaterial color={FRAME_C} roughness={0.72} /></mesh>
            ))}
          </group>
        )}

        {/* Arched door — centred lower */}
        {hasDoor && (
          <group position={[0, -H*0.06, 0]}>
            <mesh position={[0, 0, 0.010]}>
              <planeGeometry args={[DOOR_W*0.90, DOOR_H*0.94]} />
              <meshStandardMaterial color="#3A2010" roughness={0.82} />
            </mesh>
            <mesh geometry={doorFrameGeo} castShadow>
              <meshStandardMaterial color={FRAME_C} roughness={0.70} />
            </mesh>
          </group>
        )}
      </group>
    </>
  );
}

/* Fired brick wall — full height, ONE centred Georgian window OR arched door */
function BrickVisual({ slot }) {
  const [W, H, D] = slot.sz;
  const isX = W < D;
  const geo = useMemo(() => {
    const g = new THREE.BoxGeometry(W, H, D, 3, 4, 1);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const n = (sr(i*13+slot.id*9) - 0.5) * 0.012;
      p.setXYZ(i, p.getX(i)+n, p.getY(i)+n*0.6, p.getZ(i)+n);
    }
    g.computeVertexNormals();
    return g;
  }, [W, H, D, slot.id]);

  /* Georgian 6-pane window (3×2): wider + taller than cottage 4-pane */
  const WIN_W = 0.54, WIN_H = 0.66, FRAME = 0.052;
  const FRAME_C = '#2A1608';
  // Deep Victorian red-brown — muted, not orange
  const BRICK_C = '#7A3228';

  /* Sign-aware exterior face direction */
  const extSign = isX ? Math.sign(slot.pos[0]) : Math.sign(slot.pos[2]);
  const faceOffset = isX
    ? [extSign * (W/2 + 0.015), 0, 0]
    : [0, 0, extSign * (D/2 + 0.015)];
  const faceRot = isX
    ? [0, extSign > 0 ? Math.PI/2 : -Math.PI/2, 0]
    : [0, extSign > 0 ? 0 : Math.PI, 0];

  /* Door arch */
  const DOOR_W = 0.52, DOOR_H = 0.82;

  return (
    <>
      <mesh geometry={geo} castShadow receiveShadow>
        <meshStandardMaterial color={BRICK_C} roughness={0.90} metalness={0.02} />
      </mesh>

      {/* Horizontal brick belt — decorative band ~1/3 up the wall */}
      <mesh position={[0, -H*0.18, 0]}>
        <boxGeometry args={[W+0.008, 0.044, D+0.008]} />
        <meshStandardMaterial color="#3C1008" roughness={0.94} />
      </mesh>

      <group position={faceOffset} rotation={faceRot}>
        {/* ONE centred Georgian 6-pane window (3 cols × 2 rows) */}
        {slot.hasWindow && (
          <group position={[0, H*0.12, 0]}>
            {/* Luminous warm-white glass */}
            <mesh position={[0, 0, 0.018]}>
              <planeGeometry args={[WIN_W, WIN_H]} />
              <meshStandardMaterial
                color="#FFF4D0"
                emissive="#FFD870"
                emissiveIntensity={2.8}
                roughness={0.10} metalness={0.25}
                transparent opacity={0.90}
              />
            </mesh>
            {/* 3-column dividers */}
            {[-WIN_W/3, 0, WIN_W/3].map((x,i) => (
              <mesh key={`v${i}`} position={[x, 0, 0.032]}>
                <boxGeometry args={[0.026, WIN_H, 0.050]} />
                <meshStandardMaterial color={FRAME_C} roughness={0.70} />
              </mesh>
            ))}
            {/* 2-row divider */}
            <mesh position={[0, 0, 0.032]}>
              <boxGeometry args={[WIN_W, 0.026, 0.050]} />
              <meshStandardMaterial color={FRAME_C} roughness={0.70} />
            </mesh>
            {/* Frame surround */}
            {[[0,WIN_H/2+FRAME/2],[0,-(WIN_H/2+FRAME/2)]].map(([fx,fy],j)=>(
              <mesh key={j} position={[fx,fy,0.038]} castShadow>
                <boxGeometry args={[WIN_W+FRAME*2, FRAME, 0.058]} />
                <meshStandardMaterial color={FRAME_C} roughness={0.70} />
              </mesh>
            ))}
            {[[-(WIN_W/2+FRAME/2),0],[WIN_W/2+FRAME/2,0]].map(([fx,fy],j)=>(
              <mesh key={j} position={[fx,fy,0.038]} castShadow>
                <boxGeometry args={[FRAME, WIN_H+FRAME*2, 0.058]} />
                <meshStandardMaterial color={FRAME_C} roughness={0.70} />
              </mesh>
            ))}
            {/* Stone lintel above window */}
            <mesh position={[0, WIN_H/2+FRAME+0.022, 0.020]} castShadow>
              <boxGeometry args={[WIN_W+FRAME*2+0.06, 0.044, 0.048]} />
              <meshStandardMaterial color="#9A8878" roughness={0.90} />
            </mesh>
            {/* Wooden shutters flanking window — classic Georgian detail */}
            {[-(WIN_W/2+FRAME+0.058), WIN_W/2+FRAME+0.058].map((sx, si) => (
              <mesh key={`sh-${si}`} position={[sx, 0, 0.024]} castShadow>
                <boxGeometry args={[0.096, WIN_H+FRAME*0.6, 0.022]} />
                <meshStandardMaterial color="#2A1608" roughness={0.80} />
              </mesh>
            ))}
            {/* Shutter louvre lines — 5 thin horizontal slats on each shutter */}
            {[-(WIN_W/2+FRAME+0.058), WIN_W/2+FRAME+0.058].map((sx, si) =>
              [-0.22,-0.11,0,0.11,0.22].map((ry, ri) => (
                <mesh key={`sl-${si}-${ri}`} position={[sx, ry*(WIN_H*0.36), 0.038]}>
                  <boxGeometry args={[0.090, 0.010, 0.008]} />
                  <meshStandardMaterial color="#180A04" roughness={0.85} />
                </mesh>
              ))
            )}
          </group>
        )}

        {/* Arched door — centred lower */}
        {slot.hasDoor && (
          <group position={[0, -H*0.14, 0]}>
            {/* Wooden door fill — dark rich wood */}
            <mesh position={[0, -DOOR_H*0.04, 0.012]} castShadow>
              <planeGeometry args={[DOOR_W, DOOR_H*0.88]} />
              <meshStandardMaterial color="#2C1208" roughness={0.84} />
            </mesh>
            {/* Upper raised door panel */}
            <mesh position={[0, DOOR_H*0.18, 0.026]} castShadow>
              <boxGeometry args={[DOOR_W*0.56, DOOR_H*0.26, 0.014]} />
              <meshStandardMaterial color="#1C0C06" roughness={0.88} />
            </mesh>
            {/* Lower raised door panel */}
            <mesh position={[0, -DOOR_H*0.18, 0.026]} castShadow>
              <boxGeometry args={[DOOR_W*0.56, DOOR_H*0.24, 0.014]} />
              <meshStandardMaterial color="#1C0C06" roughness={0.88} />
            </mesh>
            {/* Brass knocker */}
            <mesh position={[0, DOOR_H*0.02, 0.036]} castShadow>
              <sphereGeometry args={[0.022, 8, 8]} />
              <meshStandardMaterial color="#C89030" metalness={0.90} roughness={0.18} emissive="#FFD060" emissiveIntensity={0.6}/>
            </mesh>

            {/* CLASSICAL DOOR FRAME: Pilasters + semi-circular torus arch */}
            {/* Left pilaster column */}
            <mesh position={[-(DOOR_W*0.5 + 0.046), -DOOR_H*0.04, 0.055]} castShadow>
              <boxGeometry args={[0.084, DOOR_H*0.90, 0.072]} />
              <meshStandardMaterial color="#3A1E0A" roughness={0.72} />
            </mesh>
            {/* Right pilaster column */}
            <mesh position={[ DOOR_W*0.5 + 0.046, -DOOR_H*0.04, 0.055]} castShadow>
              <boxGeometry args={[0.084, DOOR_H*0.90, 0.072]} />
              <meshStandardMaterial color="#3A1E0A" roughness={0.72} />
            </mesh>
            {/* Horizontal spring-line bar (where arch meets pilasters) */}
            <mesh position={[0, DOOR_H*0.41, 0.058]} castShadow>
              <boxGeometry args={[DOOR_W + 0.26, 0.062, 0.076]} />
              <meshStandardMaterial color="#3A1E0A" roughness={0.72} />
            </mesh>
            {/* Semi-circular torus arch above spring line */}
            {/* TorusGeometry(R, tube, radSeg, tubeSeg, arc): arc=PI = top semi-circle */}
            <mesh position={[0, DOOR_H*0.41, 0.055]} castShadow>
              <torusGeometry args={[DOOR_W*0.5 + 0.046, 0.052, 8, 22, Math.PI]} />
              <meshStandardMaterial color="#3A1E0A" roughness={0.72} />
            </mesh>
            {/* Keystone at arch apex */}
            <mesh position={[0, DOOR_H*0.41 + DOOR_W*0.5 + 0.046 + 0.012, 0.055]} castShadow>
              <boxGeometry args={[0.068, 0.072, 0.072]} />
              <meshStandardMaterial color="#5A3A1A" roughness={0.78} />
            </mesh>

            {/* Warm glow strip above door (light from inside seeping out at top) */}
            <mesh position={[0, DOOR_H*0.41, 0.018]}>
              <planeGeometry args={[DOOR_W*0.80, 0.016]} />
              <meshStandardMaterial color="#FF9020" emissive="#FF7010" emissiveIntensity={3.0} />
            </mesh>

            {/* Point light INSIDE building */}
            <pointLight position={[0, 0, -0.80]} color="#FF9050" intensity={2.2} distance={4.0} decay={2} />
            {/* Door step sill */}
            <mesh position={[0, -DOOR_H*0.5-0.028, 0.030]} castShadow receiveShadow>
              <boxGeometry args={[DOOR_W+0.32, 0.056, 0.14]} />
              <meshStandardMaterial color="#3A2818" roughness={0.85} />
            </mesh>
            {/* Door mat — dark coir rectangle on the step */}
            <mesh position={[0, -DOOR_H*0.5-0.030, 0.100]} receiveShadow>
              <boxGeometry args={[DOOR_W*0.76, 0.009, 0.22]} />
              <meshStandardMaterial color="#2A1E0C" roughness={0.98} />
            </mesh>
            {/* Mat stripe pattern — two lighter horizontal stripes */}
            {[-0.038, 0.038].map((my, mi) => (
              <mesh key={`ms-${mi}`} position={[0, -DOOR_H*0.5-0.026, 0.100+my]}>
                <boxGeometry args={[DOOR_W*0.68, 0.010, 0.020]} />
                <meshStandardMaterial color="#4A3418" roughness={0.97} />
              </mesh>
            ))}
            {/* Wall lanterns flanking arch — warm amber sconces */}
            {[-(DOOR_W*0.5 + 0.22), DOOR_W*0.5 + 0.22].map((lx, li) => (
              <group key={`lamp-${li}`} position={[lx, DOOR_H*0.24, 0.058]}>
                {/* Lantern box housing */}
                <mesh castShadow>
                  <boxGeometry args={[0.052, 0.082, 0.052]} />
                  <meshStandardMaterial color="#2A1A08" metalness={0.55} roughness={0.45} />
                </mesh>
                {/* Glowing bulb inside */}
                <mesh position={[0, 0, 0]}>
                  <sphereGeometry args={[0.018, 8, 8]} />
                  <meshStandardMaterial
                    color="#FFF0A0"
                    emissive="#FFD060"
                    emissiveIntensity={5.0}
                  />
                </mesh>
                {/* Bracket arm from wall */}
                <mesh position={[li === 0 ? 0.030 : -0.030, -0.010, -0.022]}>
                  <boxGeometry args={[0.060, 0.016, 0.044]} />
                  <meshStandardMaterial color="#2A1A08" metalness={0.55} roughness={0.45} />
                </mesh>
                <pointLight position={[0, -0.04, 0.06]} color="#FFD060" intensity={1.0} distance={2.0} decay={2} />
              </group>
            ))}
          </group>
        )}
      </group>
    </>
  );
}

/* Stone chimney — tapered */
function ChimneyVisual({ slot }) {
  const [W,,D] = slot.sz;
  const geo = useMemo(() => {
    const g = new THREE.BoxGeometry(W, slot.sz[1], D, 2, 3, 2);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const t = (p.getY(i) / slot.sz[1] + 0.5); // 0 at bottom, 1 at top
      const scale = 1 - t * 0.12; // taper upward
      const n = (sr(i*17+slot.id*3)-0.5)*0.018;
      p.setXYZ(i, p.getX(i)*scale+n, p.getY(i), p.getZ(i)*scale+n);
    }
    g.computeVertexNormals();
    return g;
  }, [slot.sz, slot.id]);
  return (
    <>
      <mesh geometry={geo} castShadow receiveShadow>
        <meshStandardMaterial color="#9A9080" roughness={0.90} metalness={0.02} />
      </mesh>
      {/* Cap */}
      <mesh position={[0, slot.sz[1]/2+0.022, 0]} castShadow>
        <boxGeometry args={[W+0.04, 0.044, D+0.04]} />
        <meshStandardMaterial color="#6A6058" roughness={0.85} />
      </mesh>
    </>
  );
}

/* Castle/manor tower stone block */
function TowerVisual({ slot }) {
  const [W, H, D] = slot.sz;
  const isTopBlock = slot.si === 4 && slot.pos[1] > 2.5;
  const geo = useMemo(() => {
    const g = new THREE.BoxGeometry(W, H, D, 4, 2, 4);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const n = (sr(i*13.7+slot.id*5.3)-0.5)*0.032;
      p.setXYZ(i, p.getX(i)+n, p.getY(i)+n*0.5, p.getZ(i)+n);
    }
    g.computeVertexNormals();
    return g;
  }, [W, H, D, slot.id]);
  const stoneColor = slot.si <= 3 ? '#A89878' : '#625444';
  return (
    <>
      <mesh geometry={geo} castShadow receiveShadow>
        <meshStandardMaterial color={stoneColor} roughness={0.88} metalness={0.03} />
      </mesh>
      {/* Battlements on top-most tower block */}
      {isTopBlock && [[-0.38,0.32],[ 0.38,0.32],[0,-0.32]].map(([bx,bz],i)=>(
        <mesh key={i} position={[bx, H/2+0.15, bz]} castShadow>
          <boxGeometry args={[0.22, 0.28, 0.22]} />
          <meshStandardMaterial color={stoneColor} roughness={0.88} metalness={0.03} />
        </mesh>
      ))}
    </>
  );
}

/* ═══ MANOR VISUAL COMPONENTS ═══════════════════════════════════════════ */

/* Reusable tall 3×3-pane window with warm amber glass, walnut frame + shutters */
function TallWindow({ pos = [0,0,0], winW = 0.46, winH = 0.68 }) {
  const FT = 0.048, FRAME = '#1E1610', STONE = '#C8BC98', WALNUT = '#7A4828';
  return (
    <group position={pos}>
      <mesh position={[0, 0, 0.018]}>
        <planeGeometry args={[winW, winH]} />
        <meshStandardMaterial color="#FFE8A8" emissive="#FFD060" emissiveIntensity={2.6}
          roughness={0.10} metalness={0.20} transparent opacity={0.90} />
      </mesh>
      {[-winW/3, winW/3].map((x,i)=>(
        <mesh key={`v${i}`} position={[x,0,0.030]}>
          <boxGeometry args={[0.022,winH,0.044]} />
          <meshStandardMaterial color={FRAME} roughness={0.72}/>
        </mesh>
      ))}
      {[-winH/3, winH/3].map((y,i)=>(
        <mesh key={`h${i}`} position={[0,y,0.030]}>
          <boxGeometry args={[winW,0.020,0.044]} />
          <meshStandardMaterial color={FRAME} roughness={0.72}/>
        </mesh>
      ))}
      {[[0, winH/2+FT/2],[0,-(winH/2+FT/2)]].map(([fx,fy],i)=>(
        <mesh key={`ft${i}`} position={[fx,fy,0.034]}>
          <boxGeometry args={[winW+FT*2,FT,0.054]} />
          <meshStandardMaterial color={FRAME} roughness={0.72}/>
        </mesh>
      ))}
      {[[-(winW/2+FT/2),0],[winW/2+FT/2,0]].map(([fx,fy],i)=>(
        <mesh key={`fs${i}`} position={[fx,fy,0.034]}>
          <boxGeometry args={[FT,winH+FT*2,0.054]} />
          <meshStandardMaterial color={FRAME} roughness={0.72}/>
        </mesh>
      ))}
      <mesh position={[0,winH/2+FT+0.022,0.018]} castShadow>
        <boxGeometry args={[winW+FT*2+0.06,0.044,0.044]} />
        <meshStandardMaterial color={STONE} roughness={0.88}/>
      </mesh>
      <mesh position={[0,-(winH/2+FT+0.016),0.018]}>
        <boxGeometry args={[winW+FT*2+0.04,0.030,0.050]} />
        <meshStandardMaterial color={STONE} roughness={0.88}/>
      </mesh>
      {[-(winW/2+FT+0.052), winW/2+FT+0.052].map((sx,si)=>(
        <mesh key={`sh${si}`} position={[sx,0,0.022]}>
          <boxGeometry args={[0.088,winH+FT*0.4,0.018]} />
          <meshStandardMaterial color={WALNUT} roughness={0.80}/>
        </mesh>
      ))}
    </group>
  );
}

/* Cream rendered plaster manor wall — walnut cladding bands + tall windows or grand door */
function ManorWallVisual({ slot }) {
  const [W, H, D] = slot.sz;
  const isX   = W < D;
  const CREAM  = '#D8CC9E', WALNUT = '#7A4828', STONE = '#C8BC98';
  const DOOR_C = '#1A0E08', DOOR_F = '#3A2410';

  const wallGeo = useMemo(() => {
    const g = new THREE.BoxGeometry(W,H,D,2,2,1);
    const p = g.attributes.position;
    for (let i=0;i<p.count;i++) {
      const n=(sr(i*11+slot.id*7)-0.5)*0.005;
      p.setXYZ(i,p.getX(i)+n,p.getY(i)+n,p.getZ(i)+n);
    }
    g.computeVertexNormals(); return g;
  }, [W,H,D,slot.id]);

  const longDim = isX ? D : W;
  const extSign = isX ? Math.sign(slot.pos[0]) : Math.sign(slot.pos[2]);
  const faceOffset = isX
    ? [extSign*(W/2+0.016), 0, 0]
    : [0, 0, extSign*(D/2+0.016)];
  const faceRot = isX
    ? [0, extSign>0 ? Math.PI/2 : -Math.PI/2, 0]
    : [0, extSign>0 ? 0 : Math.PI, 0];

  // Window positions in face-local X, Y (WIN_Y centred slightly above mid)
  const WIN_Y  = H * 0.03;
  const WIN_X1 = -longDim * 0.23;
  const WIN_X2 =  longDim * 0.23;
  // Door dims
  const DOOR_W = 0.72, DOOR_H = 1.06;

  return (
    <>
      <mesh geometry={wallGeo} castShadow receiveShadow>
        <meshStandardMaterial color={CREAM} roughness={0.84} />
      </mesh>
      <group position={faceOffset} rotation={faceRot}>
        {/* Top cornice strip */}
        <mesh position={[0, H/2-0.038, 0]} castShadow>
          <boxGeometry args={[longDim+0.04, 0.076, 0.040]} />
          <meshStandardMaterial color={STONE} roughness={0.80}/>
        </mesh>
        {/* Bottom base strip */}
        <mesh position={[0, -H/2+0.036, 0]} castShadow>
          <boxGeometry args={[longDim+0.04, 0.072, 0.038]} />
          <meshStandardMaterial color={STONE} roughness={0.80}/>
        </mesh>
        {/* 3 walnut horizontal cladding bands */}
        {[-0.24, 0.02, 0.26].map((rel,i)=>(
          <mesh key={i} position={[0, rel*H, 0]}>
            <boxGeometry args={[longDim+0.02, H*0.085, 0.024]} />
            <meshStandardMaterial color={WALNUT} roughness={0.76}/>
          </mesh>
        ))}
        {/* Plain side-wall windows */}
        {slot.hasWindow && !slot.hasDoor && (
          <>
            <TallWindow pos={[WIN_X1, WIN_Y, 0]} />
            <TallWindow pos={[WIN_X2, WIN_Y, 0]} />
          </>
        )}
        {/* Grand entrance — double door + flanking windows + portico surround */}
        {slot.hasDoor && (
          <group position={[0, -H*0.04, 0]}>
            {/* Dark wood double door fill */}
            <mesh position={[0,-DOOR_H*0.04,0.012]}>
              <planeGeometry args={[DOOR_W, DOOR_H*0.88]} />
              <meshStandardMaterial color={DOOR_C} roughness={0.84}/>
            </mesh>
            {/* Centre divider */}
            <mesh position={[0,-DOOR_H*0.04,0.026]}>
              <boxGeometry args={[0.016,DOOR_H*0.86,0.024]} />
              <meshStandardMaterial color="#0E0806" roughness={0.90}/>
            </mesh>
            {/* Raised panels */}
            {[-DOOR_W*0.25, DOOR_W*0.25].map((px,i)=>(
              <React.Fragment key={i}>
                <mesh position={[px, DOOR_H*0.12, 0.026]}>
                  <boxGeometry args={[DOOR_W*0.38,DOOR_H*0.28,0.012]} />
                  <meshStandardMaterial color="#100804" roughness={0.88}/>
                </mesh>
                <mesh position={[px,-DOOR_H*0.18,0.026]}>
                  <boxGeometry args={[DOOR_W*0.38,DOOR_H*0.22,0.012]} />
                  <meshStandardMaterial color="#100804" roughness={0.88}/>
                </mesh>
              </React.Fragment>
            ))}
            {/* Transom / fanlight */}
            <mesh position={[0,DOOR_H*0.50,0.016]}>
              <planeGeometry args={[DOOR_W*0.86,DOOR_H*0.16]} />
              <meshStandardMaterial color="#FFE8A8" emissive="#FFD060" emissiveIntensity={2.4} transparent opacity={0.90} roughness={0.10}/>
            </mesh>
            {/* Pilasters */}
            {[-(DOOR_W/2+0.052), DOOR_W/2+0.052].map((px,i)=>(
              <mesh key={i} position={[px,DOOR_H*0.08,0.054]} castShadow>
                <boxGeometry args={[0.092,DOOR_H*0.96,0.074]} />
                <meshStandardMaterial color={DOOR_F} roughness={0.72}/>
              </mesh>
            ))}
            {/* Entablature */}
            <mesh position={[0,DOOR_H*0.60,0.058]} castShadow>
              <boxGeometry args={[DOOR_W+0.30,0.066,0.082]} />
              <meshStandardMaterial color={DOOR_F} roughness={0.72}/>
            </mesh>
            {/* Brass handles */}
            {[-DOOR_W*0.12, DOOR_W*0.12].map((hx,i)=>(
              <mesh key={i} position={[hx,-DOOR_H*0.02,0.038]}>
                <sphereGeometry args={[0.018,8,8]} />
                <meshStandardMaterial color="#C89030" metalness={0.90} roughness={0.18} emissive="#FFD060" emissiveIntensity={0.5}/>
              </mesh>
            ))}
            {/* Door step */}
            <mesh position={[0,-DOOR_H*0.50-0.030,0.036]} castShadow>
              <boxGeometry args={[DOOR_W+0.44,0.060,0.18]} />
              <meshStandardMaterial color="#A09070" roughness={0.86}/>
            </mesh>
            {/* Wall lanterns */}
            {[-(DOOR_W/2+0.30), DOOR_W/2+0.30].map((lx,li)=>(
              <group key={li} position={[lx,DOOR_H*0.28,0.062]}>
                <mesh castShadow>
                  <boxGeometry args={[0.056,0.092,0.056]} />
                  <meshStandardMaterial color="#2A1A08" metalness={0.55} roughness={0.45}/>
                </mesh>
                <mesh>
                  <sphereGeometry args={[0.020,8,8]} />
                  <meshStandardMaterial color="#FFF0A0" emissive="#FFD060" emissiveIntensity={5.0}/>
                </mesh>
                <pointLight position={[0,-0.05,0.08]} color="#FFD060" intensity={1.2} distance={2.5} decay={2}/>
              </group>
            ))}
            {/* Flanking windows */}
            <TallWindow pos={[-1.35, WIN_Y+H*0.04, 0]} />
            <TallWindow pos={[ 1.35, WIN_Y+H*0.04, 0]} />
            {/* Interior warm light */}
            <pointLight position={[0,0,-0.90]} color="#FF9050" intensity={2.5} distance={5.0} decay={2}/>
          </group>
        )}
      </group>
    </>
  );
}

/* Decorative cornice belt — cream frame strips + walnut accent line */
function ManorCorniceVisual({ slot }) {
  const [W,,D] = slot.sz;
  const H = slot.sz[1];
  const CREAM = '#C8BC98', WALNUT = '#7A4828';
  const T = 0.30; // strip thickness
  return (
    <>
      <mesh position={[0,0, D/2-T/2]} castShadow>
        <boxGeometry args={[W+0.04,H+0.018,T]} />
        <meshStandardMaterial color={CREAM} roughness={0.80}/>
      </mesh>
      <mesh position={[0,0,-(D/2-T/2)]} castShadow>
        <boxGeometry args={[W+0.04,H+0.018,T]} />
        <meshStandardMaterial color={CREAM} roughness={0.80}/>
      </mesh>
      <mesh position={[-(W/2-T/2),0,0]} castShadow>
        <boxGeometry args={[T,H+0.018,D+0.04]} />
        <meshStandardMaterial color={CREAM} roughness={0.80}/>
      </mesh>
      <mesh position={[W/2-T/2,0,0]} castShadow>
        <boxGeometry args={[T,H+0.018,D+0.04]} />
        <meshStandardMaterial color={CREAM} roughness={0.80}/>
      </mesh>
      <mesh position={[0,-H*0.36,0]}>
        <boxGeometry args={[W+0.08,0.022,D+0.08]} />
        <meshStandardMaterial color={WALNUT} roughness={0.76}/>
      </mesh>
    </>
  );
}

/* Classical portico — 4 Doric columns + entablature + 3 steps */
function ManorPorchVisual({ slot }) {
  const [W,H,D] = slot.sz; // 2.80, 1.32, 0.90
  const CREAM = '#E8DFC8', STONE = '#C8BC98', WALNUT = '#7A4828';
  const COL_R = 0.070;
  const COL_XS = [-W*0.40,-W*0.135,W*0.135,W*0.40];
  return (
    <>
      {COL_XS.map((cx,i)=>(
        <group key={i} position={[cx,0,D/2-0.12]}>
          <mesh castShadow>
            <cylinderGeometry args={[COL_R*0.82,COL_R,H,12,4]} />
            <meshStandardMaterial color={CREAM} roughness={0.78}/>
          </mesh>
          <mesh position={[0,-H/2+0.025,0]} castShadow>
            <boxGeometry args={[COL_R*2.6,0.050,COL_R*2.6]} />
            <meshStandardMaterial color={STONE} roughness={0.82}/>
          </mesh>
          <mesh position={[0,H/2-0.038,0]} castShadow>
            <boxGeometry args={[COL_R*2.9,0.076,COL_R*2.9]} />
            <meshStandardMaterial color={STONE} roughness={0.80}/>
          </mesh>
        </group>
      ))}
      {/* Entablature */}
      <mesh position={[0,H/2-0.044,D/2-0.12]} castShadow>
        <boxGeometry args={[W+0.08,0.092,D*0.60]} />
        <meshStandardMaterial color={STONE} roughness={0.80}/>
      </mesh>
      {/* Walnut frieze band */}
      <mesh position={[0,H/2-0.138,D/2-0.10]}>
        <boxGeometry args={[W+0.06,0.048,0.028]} />
        <meshStandardMaterial color={WALNUT} roughness={0.78}/>
      </mesh>
      {/* Porch floor */}
      <mesh position={[0,-H/2+0.020,0]} castShadow receiveShadow>
        <boxGeometry args={[W+0.10,0.040,D+0.10]} />
        <meshStandardMaterial color={STONE} roughness={0.86}/>
      </mesh>
      {/* 3 steps descending from porch */}
      {[0,1,2].map(i=>(
        <mesh key={i} position={[0,-H/2-i*0.042,D/2+0.06+i*0.080]} castShadow receiveShadow>
          <boxGeometry args={[W*0.70+i*0.12,0.042,0.14+i*0.02]} />
          <meshStandardMaterial color={STONE} roughness={0.86}/>
        </mesh>
      ))}
    </>
  );
}

/* 2nd-floor balcony — stone slab + walnut railing posts + top rail */
function ManorBalconyVisual({ slot }) {
  const [W,H,D] = slot.sz; // 3.40, 0.08, 1.00
  const WALNUT = '#7A4828', STONE = '#C8BC98';
  const N = Math.max(2, Math.round(W/0.28));
  const SP = W/(N-1);
  return (
    <>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[W,H,D]} />
        <meshStandardMaterial color={STONE} roughness={0.85}/>
      </mesh>
      {/* Slab front edge trim */}
      <mesh position={[0,-H/2-0.012,D/2-0.042]}>
        <boxGeometry args={[W+0.04,0.024,0.082]} />
        <meshStandardMaterial color={WALNUT} roughness={0.78}/>
      </mesh>
      {/* Railing posts */}
      {Array.from({length:N},(_,i)=>(
        <mesh key={i} position={[-W/2+i*SP, H/2+0.22, D/2-0.062]} castShadow>
          <boxGeometry args={[0.022,0.44,0.022]} />
          <meshStandardMaterial color={WALNUT} roughness={0.76}/>
        </mesh>
      ))}
      {/* Top rail */}
      <mesh position={[0,H/2+0.44,D/2-0.062]} castShadow>
        <boxGeometry args={[W+0.02,0.032,0.038]} />
        <meshStandardMaterial color={WALNUT} roughness={0.74}/>
      </mesh>
      {/* Bottom rail */}
      <mesh position={[0,H/2+0.04,D/2-0.062]}>
        <boxGeometry args={[W+0.02,0.022,0.030]} />
        <meshStandardMaterial color={WALNUT} roughness={0.78}/>
      </mesh>
      {/* Corner posts (taller) */}
      {[-W/2,W/2].map((px,i)=>(
        <mesh key={i} position={[px,H/2+0.28,D/2-0.062]} castShadow>
          <boxGeometry args={[0.038,0.56,0.038]} />
          <meshStandardMaterial color={WALNUT} roughness={0.70} metalness={0.05}/>
        </mesh>
      ))}
    </>
  );
}

/* Parapet wall + corner caps — crowns the 2nd floor */
function ManorParapetVisual({ slot }) {
  const [W,,D] = slot.sz;
  const H = slot.sz[1]; // 0.26
  const CREAM = '#D8CC9E', WALNUT = '#7A4828', STONE = '#C8BC98';
  const T = 0.28;
  const strips = [
    {pos:[0,0, D/2-T/2],     args:[W+0.04,H+0.02,T]},
    {pos:[0,0,-(D/2-T/2)],   args:[W+0.04,H+0.02,T]},
    {pos:[-(W/2-T/2),0,0],   args:[T,H+0.02,D+0.04]},
    {pos:[ W/2-T/2, 0,0],    args:[T,H+0.02,D+0.04]},
  ];
  const corners = [
    [-W/2+T/2, D/2-T/2],[ W/2-T/2, D/2-T/2],
    [-W/2+T/2,-(D/2-T/2)],[ W/2-T/2,-(D/2-T/2)],
  ];
  return (
    <>
      {strips.map(({pos,args},i)=>(
        <mesh key={i} position={pos} castShadow>
          <boxGeometry args={args} />
          <meshStandardMaterial color={CREAM} roughness={0.84}/>
        </mesh>
      ))}
      {corners.map(([px,pz],i)=>(
        <mesh key={`c${i}`} position={[px,H/2+0.06,pz]} castShadow>
          <boxGeometry args={[T+0.06,0.14,T+0.06]} />
          <meshStandardMaterial color={STONE} roughness={0.80}/>
        </mesh>
      ))}
      {/* Walnut top cap */}
      <mesh position={[0,H/2+0.006,0]}>
        <boxGeometry args={[W+0.12,0.016,D+0.12]} />
        <meshStandardMaterial color={WALNUT} roughness={0.72}/>
      </mesh>
    </>
  );
}

/* ═══ VILLA (MODERN) VISUAL COMPONENTS ═══════════════════════════════════ */

/* Modern white concrete wall — wide tinted-glass panels, dark charcoal frames */
function ModernWallVisual({ slot }) {
  const [W, H, D] = slot.sz;
  const isX = W < D;
  const CONC  = '#ECEAE4';  // off-white concrete
  const BASE  = '#DDDBD5';  // slightly darker base strip
  const DARK  = '#1E1E1E';  // charcoal frames
  const GLASS = '#1A2E3C';  // dark tinted glass
  const GLOW  = '#FFB070';  // warm amber interior
  const WOOD  = '#8B5E3C';  // timber accent

  const wallGeo = useMemo(() => {
    const g = new THREE.BoxGeometry(W,H,D,1,1,1);
    const p = g.attributes.position;
    for (let i=0;i<p.count;i++) {
      const n=(sr(i*11+slot.id*7)-0.5)*0.002;
      p.setXYZ(i,p.getX(i)+n,p.getY(i)+n,p.getZ(i)+n);
    }
    g.computeVertexNormals(); return g;
  }, [W,H,D,slot.id]);

  const longDim = isX ? D : W;
  const extSign = isX ? Math.sign(slot.pos[0]) : Math.sign(slot.pos[2]);
  const faceOffset = isX
    ? [extSign*(W/2+0.014), 0, 0]
    : [0, 0, extSign*(D/2+0.014)];
  const faceRot = isX
    ? [0, extSign>0 ? Math.PI/2 : -Math.PI/2, 0]
    : [0, extSign>0 ? 0 : Math.PI, 0];

  const WIN_W = longDim * 0.72;
  const WIN_H = H * 0.60;
  const FW = 0.030;

  return (
    <>
      <mesh geometry={wallGeo} castShadow receiveShadow>
        <meshStandardMaterial color={CONC} roughness={0.88} metalness={0.02}/>
      </mesh>
      <group position={faceOffset} rotation={faceRot}>
        {/* Darker base strip */}
        <mesh position={[0,-H/2+0.040,0]}>
          <boxGeometry args={[longDim+0.02,0.080,0.016]}/>
          <meshStandardMaterial color={BASE} roughness={0.90}/>
        </mesh>
        {/* Wide panoramic window */}
        {slot.hasWindow && !slot.hasDoor && (
          <group position={[0,H*0.04,0]}>
            <mesh position={[0,0,0.014]}>
              <planeGeometry args={[WIN_W,WIN_H]}/>
              <meshStandardMaterial color={GLASS} emissive={GLOW} emissiveIntensity={0.28}
                roughness={0.04} metalness={0.62} transparent opacity={0.90}/>
            </mesh>
            {/* Frame top/bottom */}
            {[[0,WIN_H/2+FW/2],[0,-(WIN_H/2+FW/2)]].map(([fx,fy],i)=>(
              <mesh key={`ft${i}`} position={[fx,fy,0.022]}>
                <boxGeometry args={[WIN_W+FW*2,FW,0.026]}/>
                <meshStandardMaterial color={DARK} roughness={0.55} metalness={0.45}/>
              </mesh>
            ))}
            {/* Frame left/right */}
            {[[-(WIN_W/2+FW/2),0],[WIN_W/2+FW/2,0]].map(([fx,fy],i)=>(
              <mesh key={`fs${i}`} position={[fx,fy,0.022]}>
                <boxGeometry args={[FW,WIN_H+FW*2,0.026]}/>
                <meshStandardMaterial color={DARK} roughness={0.55} metalness={0.45}/>
              </mesh>
            ))}
            {/* 3-panel vertical dividers */}
            {[-WIN_W/3,0,WIN_W/3].map((x,i)=>(
              <mesh key={`vd${i}`} position={[x,0,0.020]}>
                <boxGeometry args={[0.016,WIN_H,0.018]}/>
                <meshStandardMaterial color={DARK} roughness={0.55} metalness={0.45}/>
              </mesh>
            ))}
          </group>
        )}
        {/* Glass entrance with timber accent panels */}
        {slot.hasDoor && (
          <group position={[0,-H*0.02,0]}>
            {/* Central sliding glass door */}
            <mesh position={[0,0,0.014]}>
              <planeGeometry args={[1.20,H*0.84]}/>
              <meshStandardMaterial color={GLASS} emissive={GLOW} emissiveIntensity={0.24}
                roughness={0.04} metalness={0.62} transparent opacity={0.92}/>
            </mesh>
            {/* Door centre mullion */}
            <mesh position={[0,0,0.024]}>
              <boxGeometry args={[0.018,H*0.82,0.026]}/>
              <meshStandardMaterial color={DARK} roughness={0.55} metalness={0.50}/>
            </mesh>
            {/* Door frame */}
            {[[0,H*0.42],[0,-H*0.42]].map(([fx,fy],i)=>(
              <mesh key={`df${i}`} position={[fx,fy,0.022]}>
                <boxGeometry args={[1.24,0.020,0.026]}/>
                <meshStandardMaterial color={DARK} roughness={0.55} metalness={0.50}/>
              </mesh>
            ))}
            {/* Timber accent panels */}
            {[-1.62,1.62].map((px,i)=>(
              <mesh key={`wp${i}`} position={[px,H*0.01,0.020]} castShadow>
                <boxGeometry args={[0.58,H*0.78,0.024]}/>
                <meshStandardMaterial color={WOOD} roughness={0.66}/>
              </mesh>
            ))}
            {/* Side glass */}
            {[-1.02,1.02].map((px,i)=>(
              <mesh key={`sg${i}`} position={[px,H*0.01,0.014]}>
                <planeGeometry args={[0.56,H*0.74]}/>
                <meshStandardMaterial color={GLASS} emissive={GLOW} emissiveIntensity={0.18}
                  roughness={0.04} metalness={0.62} transparent opacity={0.86}/>
              </mesh>
            ))}
            {/* Door step */}
            <mesh position={[0,-H/2-0.018,0.055]} castShadow>
              <boxGeometry args={[2.20,0.036,0.26]}/>
              <meshStandardMaterial color={BASE} roughness={0.90}/>
            </mesh>
            {/* Interior light */}
            <pointLight position={[0,0,-1.0]} color="#FFB070" intensity={3.0} distance={7.0} decay={2}/>
          </group>
        )}
      </group>
    </>
  );
}

/* Cantilevered floor slab */
function ModernSlabVisual({ slot }) {
  const [W,,D] = slot.sz;
  const H = slot.sz[1];
  const SLAB = '#D4D2CC', EDGE = '#1A1A1A';
  return (
    <>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[W,H,D]}/>
        <meshStandardMaterial color={SLAB} roughness={0.86} metalness={0.04}/>
      </mesh>
      {/* Dark shadow-line edge at bottom */}
      <mesh position={[0,-H/2-0.009,0]}>
        <boxGeometry args={[W+0.02,0.018,D+0.02]}/>
        <meshStandardMaterial color={EDGE} roughness={0.65} metalness={0.35}/>
      </mesh>
    </>
  );
}

/* Dispatcher — picks the right visual for each block */
function BlockMesh({ slot, state }) {
  const goldMatRef = useRef();

  const Visual = useMemo(() => {
    switch (slot.comp) {
      case 'post':    return PostVisual;
      case 'wicker':  return WickerVisual;
      case 'stone':   return StoneVisual;
      case 'plaster': return PlasterVisual;
      case 'brick':   return BrickVisual;
      case 'chimney':       return ChimneyVisual;
      case 'tower':         return TowerVisual;
      case 'manor_wall':    return ManorWallVisual;
      case 'manor_cornice': return ManorCorniceVisual;
      case 'manor_porch':   return ManorPorchVisual;
      case 'manor_balcony': return ManorBalconyVisual;
      case 'manor_parapet': return ManorParapetVisual;
      case 'modern_wall':   return ModernWallVisual;
      case 'modern_slab':   return ModernSlabVisual;
      default:              return StoneVisual;
    }
  }, [slot.comp]);

  return (
    <AnimatedBlock slot={slot} state={state} goldMatRef={goldMatRef}>
      <Visual slot={slot} />
    </AnimatedBlock>
  );
}

/* ═══ DUST + FLASH ═══════════════════════════════════════════════════════ */
const DUST_N = 54;
function DustSystem({ onFireRef }) {
  const ptsRef  = useRef();
  const vel     = useRef(new Float32Array(DUST_N * 3));
  const active  = useRef(false);
  const elapsed = useRef(0);
  const initBuf = useMemo(() => new Float32Array(DUST_N * 3), []);

  useEffect(() => {
    onFireRef.current = (pos) => {
      if (!ptsRef.current) return;
      const buf = ptsRef.current.geometry.attributes.position.array;
      const v   = vel.current;
      for (let i = 0; i < DUST_N; i++) {
        buf[i*3]=pos[0]; buf[i*3+1]=pos[1]; buf[i*3+2]=pos[2];
        const a=Math.random()*Math.PI*2, e=Math.random()*Math.PI*0.52, s=1.6+Math.random()*2.8;
        v[i*3]=Math.cos(a)*Math.sin(e)*s; v[i*3+1]=Math.cos(e)*s*0.68; v[i*3+2]=Math.sin(a)*Math.sin(e)*s;
      }
      ptsRef.current.geometry.attributes.position.needsUpdate = true;
      ptsRef.current.material.opacity = 0.92;
      active.current=true; elapsed.current=0;
    };
  }, [onFireRef]);

  useFrame((_,dt) => {
    if (!active.current || !ptsRef.current) return;
    elapsed.current += dt;
    const buf=ptsRef.current.geometry.attributes.position.array, v=vel.current;
    for (let i=0;i<DUST_N;i++) {
      buf[i*3]+=v[i*3]*dt; buf[i*3+1]+=v[i*3+1]*dt; buf[i*3+2]+=v[i*3+2]*dt;
      v[i*3+1]-=4.8*dt;
    }
    ptsRef.current.geometry.attributes.position.needsUpdate=true;
    ptsRef.current.material.opacity=Math.max(0,0.92*(1-elapsed.current/0.72));
    if (elapsed.current>0.85) active.current=false;
  });

  return (
    <points ref={ptsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={initBuf} count={DUST_N} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial color="#C8B090" size={0.055} sizeAttenuation transparent opacity={0} depthWrite={false} />
    </points>
  );
}

function ImpactFlash({ onFlashRef }) {
  const lRef=useRef(), active=useRef(false), elapsed=useRef(0);
  useEffect(() => {
    onFlashRef.current = (pos) => {
      if (!lRef.current) return;
      lRef.current.position.set(pos[0],pos[1]+0.25,pos[2]);
      lRef.current.intensity=6.0; active.current=true; elapsed.current=0;
    };
  }, [onFlashRef]);
  useFrame((_,dt)=>{
    if(!active.current||!lRef.current) return;
    elapsed.current+=dt;
    lRef.current.intensity=Math.max(0,6.0*(1-elapsed.current/0.16));
    if(elapsed.current>0.2) active.current=false;
  });
  return <pointLight ref={lRef} color="#D8E4FF" intensity={0} distance={5} decay={2} />;
}

/* ═══ RING METER ═════════════════════════════════════════════════════════ */
const RING_N = 64;
function RingMeter({ progress }) {
  const ref=useRef(), tmpM=useMemo(()=>new THREE.Matrix4(),[]), tmpC=useMemo(()=>new THREE.Color(),[]);
  useEffect(()=>{
    if (!ref.current) return;
    const active=Math.round(Math.min(1,progress)*RING_N);
    for (let i=0;i<RING_N;i++) {
      const a=(i/RING_N)*Math.PI*2-Math.PI*0.5;
      tmpM.makeTranslation(Math.cos(a)*3.4,0,Math.sin(a)*3.4);
      ref.current.setMatrixAt(i,tmpM);
      const on=i<active, t=i/RING_N;
      tmpC.setRGB(on?0.26+t*0.56:0.07,on?0.18+t*0.40:0.055,on?0.02+t*0.08:0.04);
      ref.current.setColorAt(i,tmpC);
    }
    ref.current.instanceMatrix.needsUpdate=true;
    if(ref.current.instanceColor) ref.current.instanceColor.needsUpdate=true;
  },[progress,tmpM,tmpC]);
  return (
    <instancedMesh ref={ref} args={[null,null,RING_N]} position={[0,0.014,0]}>
      <cylinderGeometry args={[0.037,0.037,0.040,5]} />
      <meshStandardMaterial roughness={0.60} metalness={0.28} toneMapped={false} />
    </instancedMesh>
  );
}

/* ═══ BUILDING SHELL — roofs + trims appear by score ════════════════════ */

/* Thatched gable roof — ridge runs along Z */
function ThatchedRoof({ show, ghost }) {
  const geo = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(-1.34,0); shape.lineTo(1.34,0); shape.lineTo(0,0.96); shape.closePath();
    const g = new THREE.ExtrudeGeometry(shape, {
      depth:1.95, bevelEnabled:true, bevelSize:0.055, bevelThickness:0.055, bevelSegments:2
    });
    g.translate(0,0,-0.975);
    return g;
  }, []);
  if (!show) return null;
  const op = ghost ? 0.13 : 1.0;
  const tr = ghost;
  return (
    <group position={[0,1.84,0]}>
      <mesh geometry={geo} castShadow={!ghost}>
        {/* Warmer straw/amber, higher roughness for thatch feel */}
        <meshStandardMaterial color="#B8881E" roughness={0.98} metalness={0} transparent={tr} opacity={op} depthWrite={!ghost} />
      </mesh>
      {/* Ridge pole runs along Z (front-to-back), trimmed to stay inside eaves */}
      <mesh position={[0,0.96,0]} rotation={[Math.PI/2,0,0]} castShadow={!ghost}>
        <cylinderGeometry args={[0.038,0.038,1.86,8]} />
        <meshStandardMaterial color="#5A3A10" roughness={0.82} transparent={tr} opacity={op} depthWrite={!ghost} />
      </mesh>
      {/* Eave fascia boards — front & back (at ±Z) spanning full width in X */}
      {[-0.975, 0.975].map((z,i)=>(
        <mesh key={i} position={[0,-0.030,z]} castShadow={!ghost}>
          <boxGeometry args={[2.72, 0.070, 0.048]} />
          <meshStandardMaterial color="#4A2E0E" roughness={0.84} transparent={tr} opacity={op} depthWrite={!ghost} />
        </mesh>
      ))}
    </group>
  );
}

/* Clay tile gable roof — sits on plaster top at y=0.88 */
function ClayTileRoof({ show, ghost }) {
  const geo = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(-1.84,0); shape.lineTo(1.84,0); shape.lineTo(0,1.02); shape.closePath();
    const g = new THREE.ExtrudeGeometry(shape, {
      depth:3.18, bevelEnabled:true, bevelSize:0.06, bevelThickness:0.06, bevelSegments:2
    });
    g.translate(0,0,-1.59);
    return g;
  }, []);
  if (!show) return null;
  const op = ghost ? 0.13 : 1.0;
  const tr = ghost;
  return (
    <group position={[0,0.88,0]}>
      <mesh geometry={geo} castShadow={!ghost}>
        <meshStandardMaterial color="#C07058" roughness={0.86} metalness={0.02} transparent={tr} opacity={op} depthWrite={!ghost} />
      </mesh>
      {/* Ridge */}
      <mesh position={[0,1.02,0]} rotation={[Math.PI/2,0,0]} castShadow={!ghost}>
        <cylinderGeometry args={[0.050,0.050,3.22,8]} />
        <meshStandardMaterial color="#7A3A28" roughness={0.82} transparent={tr} opacity={op} depthWrite={!ghost} />
      </mesh>
      {/* Eave fascia */}
      {[-1.59,1.59].map((z,i)=>(
        <mesh key={i} position={[0,-0.035,z]} castShadow={!ghost}>
          <boxGeometry args={[3.72,0.085,0.060]} />
          <meshStandardMaterial color="#7A3A28" roughness={0.82} transparent={tr} opacity={op} depthWrite={!ghost} />
        </mesh>
      ))}
    </group>
  );
}
function SlateRoof({ show, ghost }) {
  const geo = useMemo(() => {
    const shape = new THREE.Shape();
    shape.moveTo(-1.90,0); shape.lineTo(1.90,0); shape.lineTo(0,1.28); shape.closePath();
    const g = new THREE.ExtrudeGeometry(shape, {
      depth:3.80, bevelEnabled:true, bevelSize:0.06, bevelThickness:0.06, bevelSegments:2
    });
    g.translate(0,0,-1.90);
    return g;
  }, []);
  if (!show) return null;
  const op = ghost ? 0.10 : 1.0;
  const tr = !!ghost;
  // Horizontal bar courses are level boxes (no slope rotation needed)
  const PEAK_H = 1.28, HALF_W = 1.90;
  const courseTs   = [0.09, 0.20, 0.31, 0.42, 0.53, 0.64, 0.75, 0.86];
  return (
    <group position={[0,1.40,0]}>
      <mesh geometry={geo} castShadow={!ghost}>
        <meshStandardMaterial color="#28201A" roughness={0.92} metalness={0.04} transparent={tr} opacity={op} depthWrite={!ghost} />
      </mesh>
      {/* Ridge along Z */}
      <mesh position={[0,1.28,0]} rotation={[Math.PI/2,0,0]} castShadow={!ghost}>
        <cylinderGeometry args={[0.048,0.048,3.74,8]} />
        <meshStandardMaterial color="#120E08" roughness={0.92} transparent={tr} opacity={op} depthWrite={!ghost} />
      </mesh>
      {/* Eave fasciae */}
      {[-1.90,1.90].map((z,i)=>(
        <mesh key={i} position={[0,-0.035,z]} castShadow={!ghost}>
          <boxGeometry args={[3.84,0.080,0.060]} />
          <meshStandardMaterial color="#120E08" roughness={0.90} transparent={tr} opacity={op} depthWrite={!ghost} />
        </mesh>
      ))}
      {/* Lead flashing strip */}
      {[-1.90,1.90].map((z,i)=>(
        <mesh key={`fl-${i}`} position={[0,-0.055,z]} castShadow={!ghost}>
          <boxGeometry args={[3.88,0.028,0.055]} />
          <meshStandardMaterial color="#5A5850" roughness={0.55} metalness={0.28} transparent={tr} opacity={op} depthWrite={!ghost} />
        </mesh>
      ))}
      {/* Slate tile courses — lie ON slope surface, protrude outward along slope normal */}
      {/* Correct approach: position at (cx,cy) on slope, rotate to match slope, protrude visibly */}
      {!ghost && (() => {
        const slopeAngle = Math.atan2(PEAK_H, HALF_W); // ≈34°
        // Slope outward normal components (right slope): nx=sin(θ)=0.56, ny=cos(θ)=0.83
        const NX = Math.sin(slopeAngle);
        const NY = Math.cos(slopeAngle);
        const THICK = 0.062; // protrusion thickness — visible from above
        return courseTs.flatMap((t, i) => {
          const cy   = t * PEAK_H;
          const cx   = HALF_W * (1 - t);
          // Offset outward by half-thickness so box doesn't clip into roof
          const ox   = NX * THICK * 0.5;
          const oy   = NY * THICK * 0.5;
          return [
            <mesh key={`cr-${i}`}
              position={[ cx + ox, cy + oy, 0]}
              rotation={[0, 0, -slopeAngle]}
              castShadow>
              <boxGeometry args={[0.095, THICK, 3.84]} />
              <meshStandardMaterial color="#7A6448" roughness={0.84} metalness={0.04} />
            </mesh>,
            <mesh key={`cl-${i}`}
              position={[-(cx + ox), cy + oy, 0]}
              rotation={[0, 0,  slopeAngle]}
              castShadow>
              <boxGeometry args={[0.095, THICK, 3.84]} />
              <meshStandardMaterial color="#7A6448" roughness={0.84} metalness={0.04} />
            </mesh>,
          ];
        });
      })()}
      {/* Gable vent / dormer window — front gable face, gives house visual character */}
      {!ghost && (
        <group position={[0, 0.56, 1.91]}>
          {/* Outer frame */}
          <mesh castShadow>
            <boxGeometry args={[0.50, 0.40, 0.040]} />
            <meshStandardMaterial color="#2A1E0C" roughness={0.86} />
          </mesh>
          {/* Luminous glass */}
          <mesh position={[0, 0, 0.026]}>
            <planeGeometry args={[0.38, 0.28]} />
            <meshStandardMaterial
              color="#FFF8D0"
              emissive="#FFD060"
              emissiveIntensity={3.0}
              roughness={0.08} metalness={0.2}
              transparent opacity={0.92}
            />
          </mesh>
          {/* Cross divider */}
          <mesh position={[0, 0, 0.032]}><boxGeometry args={[0.38, 0.026, 0.040]} /><meshStandardMaterial color="#2A1E10" roughness={0.80} /></mesh>
          <mesh position={[0, 0, 0.032]}><boxGeometry args={[0.026, 0.28, 0.040]} /><meshStandardMaterial color="#2A1E10" roughness={0.80} /></mesh>
          {/* Small pediment above */}
          <mesh position={[0, 0.24, 0.010]} castShadow>
            <boxGeometry args={[0.52, 0.048, 0.036]} />
            <meshStandardMaterial color="#9A9080" roughness={0.88} />
          </mesh>
          {/* Warm glow */}
          <pointLight position={[0, 0, 0.5]} color="#FFD060" intensity={1.5} distance={3.0} decay={2} />
        </group>
      )}
    </group>
  );
}

/* Flat concrete roof for Villa — wide cantilever + rooftop glass rail */
function VillaRoof({ show, ghost }) {
  if (!show) return null;
  const op = ghost ? 0.08 : 1.0;
  const tr = !!ghost;
  const SLAB = '#CECDCA', EDGE = '#1A1A1A', GLASS = '#B0C0CC';
  return (
    <group position={[0,2.42,0]}>
      {/* Main roof slab */}
      <mesh castShadow={!ghost}>
        <boxGeometry args={[5.60,0.14,5.00]}/>
        <meshStandardMaterial color={SLAB} roughness={0.84} metalness={0.05} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Dark bottom edge */}
      <mesh position={[0,-0.079,0]}>
        <boxGeometry args={[5.62,0.020,5.02]}/>
        <meshStandardMaterial color={EDGE} roughness={0.65} metalness={0.35} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Rooftop glass railing front + back */}
      {!ghost && [-2.50,2.50].map((z,i)=>(
        <mesh key={i} position={[0,0.14,z]}>
          <boxGeometry args={[5.58,0.30,0.018]}/>
          <meshStandardMaterial color={GLASS} roughness={0.08} metalness={0.20} transparent opacity={0.30} depthWrite={false}/>
        </mesh>
      ))}
      {!ghost && [-2.80,2.80].map((x,i)=>(
        <mesh key={i} position={[x,0.14,0]}>
          <boxGeometry args={[0.018,0.30,4.98]}/>
          <meshStandardMaterial color={GLASS} roughness={0.08} metalness={0.20} transparent opacity={0.30} depthWrite={false}/>
        </mesh>
      ))}
    </group>
  );
}

/* Mansard roof for Manor — four slope panels + flat top + front dormer */
function ManorRoof({ show, ghost }) {
  if (!show) return null;
  const op = ghost ? 0.08 : 1.0;
  const tr = !!ghost;
  // Outer overhang: ±2.34 x ±2.20. Inner flat-top: ±1.58 x ±1.50. Rise: 0.44
  const OX=2.34, OZ=2.20, IX=1.58, IZ=1.50, RISE=0.44;
  const runX=OX-IX, runZ=OZ-IZ; // 0.76, 0.70
  const lenX=Math.sqrt(runX*runX+RISE*RISE); // ≈0.877
  const lenZ=Math.sqrt(runZ*runZ+RISE*RISE); // ≈0.822
  const angX=Math.atan2(RISE,runX); // ≈30°
  const angZ=Math.atan2(RISE,runZ); // ≈32°
  const C='#2A2018', TRIM='#7A5E38', FLAT='#322A1C', CREAM='#D8CC9E';
  return (
    <group position={[0,2.54,0]}>
      {/* Front slope (+Z) */}
      <mesh position={[0,RISE/2,IZ+runZ/2]} rotation={[-angZ,0,0]} castShadow={!ghost}>
        <boxGeometry args={[OX*2+0.18,0.060,lenZ]} />
        <meshStandardMaterial color={C} roughness={0.88} metalness={0.04} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Back slope (-Z) */}
      <mesh position={[0,RISE/2,-(IZ+runZ/2)]} rotation={[angZ,0,0]} castShadow={!ghost}>
        <boxGeometry args={[OX*2+0.18,0.060,lenZ]} />
        <meshStandardMaterial color={C} roughness={0.88} metalness={0.04} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Left slope (-X) */}
      <mesh position={[-(IX+runX/2),RISE/2,0]} rotation={[0,0,angX]} castShadow={!ghost}>
        <boxGeometry args={[lenX,0.060,OZ*2+0.18]} />
        <meshStandardMaterial color={C} roughness={0.88} metalness={0.04} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Right slope (+X) */}
      <mesh position={[IX+runX/2,RISE/2,0]} rotation={[0,0,-angX]} castShadow={!ghost}>
        <boxGeometry args={[lenX,0.060,OZ*2+0.18]} />
        <meshStandardMaterial color={C} roughness={0.88} metalness={0.04} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Flat top */}
      <mesh position={[0,RISE+0.030,0]} castShadow={!ghost}>
        <boxGeometry args={[IX*2+0.06,0.060,IZ*2+0.06]} />
        <meshStandardMaterial color={FLAT} roughness={0.90} metalness={0.03} transparent={tr} opacity={op} depthWrite={!ghost}/>
      </mesh>
      {/* Eave trim — front/back */}
      {[-OZ,OZ].map((z,i)=>(
        <mesh key={`et${i}`} position={[0,-0.038,z]} castShadow={!ghost}>
          <boxGeometry args={[OX*2+0.22,0.090,0.062]} />
          <meshStandardMaterial color={TRIM} roughness={0.76} transparent={tr} opacity={op} depthWrite={!ghost}/>
        </mesh>
      ))}
      {/* Eave trim — left/right */}
      {[-OX,OX].map((x,i)=>(
        <mesh key={`es${i}`} position={[x,-0.038,0]} castShadow={!ghost}>
          <boxGeometry args={[0.062,0.090,OZ*2+0.22]} />
          <meshStandardMaterial color={TRIM} roughness={0.76} transparent={tr} opacity={op} depthWrite={!ghost}/>
        </mesh>
      ))}
      {/* Flat-top corner finials */}
      {[[-IX,IZ],[IX,IZ],[-IX,-IZ],[IX,-IZ]].map(([px,pz],i)=>(
        <mesh key={`pp${i}`} position={[px,RISE+0.18,pz]} castShadow={!ghost}>
          <boxGeometry args={[0.10,0.36,0.10]} />
          <meshStandardMaterial color={CREAM} roughness={0.84} transparent={tr} opacity={op} depthWrite={!ghost}/>
        </mesh>
      ))}
      {/* Dormer window on front slope */}
      {!ghost && (
        <group position={[0,0.14,OZ-0.08]}>
          <mesh castShadow>
            <boxGeometry args={[0.68,0.52,0.072]} />
            <meshStandardMaterial color="#2A1E0C" roughness={0.82}/>
          </mesh>
          <mesh position={[0,0,0.046]}>
            <planeGeometry args={[0.52,0.36]} />
            <meshStandardMaterial color="#FFF8D0" emissive="#FFD060" emissiveIntensity={3.2} transparent opacity={0.92} roughness={0.08}/>
          </mesh>
          <mesh position={[0,0,0.062]}><boxGeometry args={[0.52,0.026,0.042]}/><meshStandardMaterial color="#1E1610" roughness={0.80}/></mesh>
          <mesh position={[0,0,0.062]}><boxGeometry args={[0.026,0.36,0.042]}/><meshStandardMaterial color="#1E1610" roughness={0.80}/></mesh>
          <mesh position={[0,0.30,0.022]} castShadow>
            <boxGeometry args={[0.70,0.060,0.052]} />
            <meshStandardMaterial color={CREAM} roughness={0.88}/>
          </mesh>
          <pointLight position={[0,0,0.60]} color="#FFD060" intensity={1.8} distance={3.5} decay={2}/>
        </group>
      )}
    </group>
  );
}

/* Candle window glow element */
function CandleWindow({ position, rotation=[0,0,0] }) {
  const lRef=useRef();
  useFrame(({clock})=>{
    if (!lRef.current) return;
    const t=clock.elapsedTime;
    lRef.current.intensity=0.7+Math.sin(t*8.3)*0.12+Math.sin(t*13.5)*0.06;
  });
  return (
    <group position={position} rotation={rotation}>
      <mesh>
        <planeGeometry args={[0.30,0.36]} />
        <meshStandardMaterial color="#FFA030" emissive="#FF9020" emissiveIntensity={0.70} transparent opacity={0.56} />
      </mesh>
      <pointLight ref={lRef} color="#FF9A2C" intensity={0.7} distance={3.0} decay={2} />
    </group>
  );
}

/* Ground */
function Ground() {
  const geo = useMemo(()=>{
    const g=new THREE.PlaneGeometry(26,26,36,36);
    const p=g.attributes.position;
    for(let i=0;i<p.count;i++) p.setZ(i,(sr(i*7.13)-0.5)*0.046);
    g.computeVertexNormals();
    return g;
  },[]);
  return (
    <mesh geometry={geo} rotation={[-Math.PI/2,0,0]} position={[0,-0.02,0]} receiveShadow>
      <meshStandardMaterial color="#121008" roughness={0.97} metalness={0.01} />
    </mesh>
  );
}

function BuildingShell({ score, currentStage, peekStage }) {
  const isPeeking = peekStage !== null;
  const peeking   = isPeeking; // alias for sub-expressions
  const showThatch = score >= 20;
  const showClay   = score >= 42;
  const showSlate  = score >= 65 && currentStage <= 2;
  const showManor  = score >= 86 && currentStage === 3;
  const showVilla  = score >= 96 && currentStage >= 4;

  // In peek mode: show the peekStage roof solid, everything else faint.
  // Thatch = stage 0, Clay = stage 1, Slate = stage 2+
  const roofForPeek = (roofSi) => isPeeking ? roofSi === peekStage : null;
  return (
    <>
      {/* THATCH ─ hut roof */}
      {showThatch && (
        isPeeking
          ? (peekStage === 0 ? <ThatchedRoof show ghost={false} /> : <ThatchedRoof show ghost={true} />)
          : (currentStage === 0 ? <ThatchedRoof show ghost={false} /> : null)
      )}

      {/* CLAY TILE ─ cottage roof */}
      {showClay && (
        isPeeking
          ? (peekStage === 1 ? <ClayTileRoof show ghost={false} /> : <ClayTileRoof show ghost={true} />)
          : (currentStage === 1 ? <ClayTileRoof show ghost={false} /> : null)
      )}

      {/* SLATE ─ house roof */}
      {showSlate && (
        isPeeking
          ? (peekStage >= 2 ? <SlateRoof show ghost={false} /> : <SlateRoof show ghost={true} />)
          : <SlateRoof show ghost={false} />
      )}

      {/* Lights & windows — only in normal mode, follow active stage */}
      {/* HUT: fire-glow from centre */}
      {!isPeeking && score>=12 && currentStage===0 && (
        <pointLight position={[0, 0.55, 0]} color="#FF7010" intensity={1.4} distance={3.8} decay={2} />
      )}
      {/* COTTAGE: soft amber lantern from inside */}
      {!isPeeking && score>=34 && currentStage===1 && (
        <pointLight position={[0, 0.48, 0]} color="#FFD060" intensity={1.8} distance={5.0} decay={2} />
      )}
      {/* HOUSE: bright warm-white light — clearly a real home */}
      {!isPeeking && score>=56 && currentStage===2 && (
        <pointLight position={[0, 0.80, 0]} color="#FFF4E0" intensity={3.2} distance={7.0} decay={2} />
      )}
      {/* Candle windows — cottage */}
      {!isPeeking && score>=37 && currentStage>=1 && <CandleWindow position={[ 1.58,0.48,-1.10]} rotation={[0,Math.PI,0]} />}
      {!isPeeking && score>=42 && currentStage>=1 && <CandleWindow position={[-1.58,0.48,-1.10]} rotation={[0,0,0]} />}
      {/* Candle windows — house */}
      {!isPeeking && score>=56 && currentStage>=2 && <CandleWindow position={[ 1.58,0.80, 0.00]} rotation={[0,Math.PI*0.5,0]} />}
      {!isPeeking && score>=60 && currentStage>=2 && <CandleWindow position={[ 0.00,0.80,-1.58]} rotation={[0,Math.PI,0]} />}
      {!isPeeking && score>=65 && currentStage>=2 && <CandleWindow position={[-1.58,0.80, 0.00]} rotation={[0,-Math.PI*0.5,0]} />}

      {/* ── MANOR ROOF ── */}
      {showManor && (
        isPeeking
          ? (peekStage===3 ? <ManorRoof show ghost={false}/> : <ManorRoof show ghost={true}/>)
          : <ManorRoof show ghost={false}/>
      )}

      {/* ── VILLA ROOF ── */}
      {showVilla && (
        isPeeking
          ? (peekStage===4 ? <VillaRoof show ghost={false}/> : <VillaRoof show ghost={true}/>)
          : <VillaRoof show ghost={false}/>
      )}

      {/* Manor interior warm light */}
      {!isPeeking && score>=78 && currentStage===3 && (
        <pointLight position={[0,1.50,0]} color="#FFF0E8" intensity={5.2} distance={10.0} decay={2}/>
      )}
      {/* Manor candle windows */}
      {!isPeeking && score>=78 && currentStage===3 && <CandleWindow position={[-2.20,1.60,0.00]} rotation={[0,-Math.PI*0.5,0]}/>}
      {!isPeeking && score>=79 && currentStage===3 && <CandleWindow position={[ 2.20,1.60,0.00]} rotation={[0, Math.PI*0.5,0]}/>}
      {!isPeeking && score>=82 && currentStage===3 && <CandleWindow position={[ 0.00,1.60,-2.05]} rotation={[0,Math.PI,0]}/>}
      {!isPeeking && score>=84 && currentStage===3 && <CandleWindow position={[ 0.00,1.60, 2.05]} rotation={[0,0,0]}/>}

      {/* Villa interior lights */}
      {!isPeeking && score>=93 && currentStage>=4 && (
        <pointLight position={[0,0.80,0]} color="#FFB870" intensity={4.0} distance={9.0} decay={2}/>
      )}
      {!isPeeking && score>=95 && currentStage>=4 && (
        <pointLight position={[0,2.00,0]} color="#FFE4C0" intensity={3.5} distance={9.0} decay={2}/>
      )}

      <Ground />
    </>
  );
}

/* ═══ CURRENT GHOST — active block shown as faint outline when peeking at past ═ */
function CurrentGhost({ slot, opacity = 0.10 }) {
  return (
    <mesh position={slot.pos}>
      <boxGeometry args={slot.sz} />
      <meshBasicMaterial color="#E8D0A0" opacity={opacity} transparent depthWrite={false} />
    </mesh>
  );
}

/* ═══ SCENE ══════════════════════════════════════════════════════════════ */
function JourneyScene({ blockStates, fireDustRef, flashRef, score, peekStage }) {
  const currentStage = getStage(score);
  const isPeeking = peekStage !== null;
  return (
    <>
      <ambientLight intensity={0.44} color="#4A4268" />
      <directionalLight position={[-4,11,8]} intensity={2.7} color="#FFF2D8"
        castShadow shadow-mapSize-width={2048} shadow-mapSize-height={2048}
        shadow-bias={-0.0006} shadow-camera-far={44}
        shadow-camera-left={-14} shadow-camera-right={14}
        shadow-camera-top={16}  shadow-camera-bottom={-8}
      />
      <directionalLight position={[6,4,8]}  intensity={0.80} color="#FFE4B0" />
      <directionalLight position={[-3,8,-8]} intensity={0.24} color="#8090C0" />
      <directionalLight position={[4,-4,-5]} intensity={0.12} color="#203060" />
      <pointLight position={[0.3,0.9,0.5]} color="#FF9A3C" intensity={1.0} distance={5} decay={2} />

      {isPeeking ? (
        <>
          {/* PEEK MODE — selected stage solid, everything else at 5% ghost */}
          {SLOTS.map(slot => {
            const st = blockStates[slot.id];
            // Show at full if: this slot's stage = peekStage AND it has been placed/dormant
            const isSelected = slot.si === peekStage &&
              ['placed','cracked','repaired','dormant'].includes(st);
            if (isSelected) {
              return <BlockMesh key={slot.id} slot={slot} state="placed" />;
            }
            // Permanent blocks (stone) always show at 5% too
            const wasEverPlaced = ['placed','cracked','repaired','dormant'].includes(st);
            if (!wasEverPlaced) return null;
            // Everything else: faint 5% ghost box
            return <CurrentGhost key={`gh-${slot.id}`} slot={slot} opacity={0.05} />;
          })}
        </>
      ) : (
        <>
          {/* NORMAL MODE — active blocks solid, dormant hidden */}
          {SLOTS.map(slot => {
            if (blockStates[slot.id] === 'dormant') return null;
            return <BlockMesh key={slot.id} slot={slot} state={blockStates[slot.id]} />;
          })}
        </>
      )}

      <BuildingShell score={score} currentStage={currentStage} peekStage={peekStage} />
      <RingMeter progress={score/100} />
      <DustSystem  onFireRef={fireDustRef} />
      <ImpactFlash onFlashRef={flashRef}  />
    </>
  );
}

/* ═══ HUD ════════════════════════════════════════════════════════════════ */
function TitleHUD({ score, stage }) {
  return (
    <div style={{position:'absolute',top:24,left:28,fontFamily:'"Outfit",sans-serif',display:'flex',flexDirection:'column',gap:4}}>
      <span style={{fontSize:9,letterSpacing:'0.32em',color:'#C8A044',fontFamily:'monospace',textTransform:'uppercase',opacity:0.72}}>Recall · What We Built</span>
      <span style={{fontSize:32,fontWeight:700,color:'#F5EDD8',lineHeight:1.1,transition:'all 0.6s ease'}}>{STAGE_NAMES[stage]}</span>
      <span style={{fontSize:12,color:'#7A6A50',fontStyle:'italic',lineHeight:1.5,maxWidth:230,transition:'all 0.6s ease'}}>{STAGE_SUBS[stage]}</span>
      <div style={{display:'flex',alignItems:'baseline',gap:6,marginTop:8}}>
        <span style={{fontSize:22,fontWeight:600,color:'#D4A855',fontFamily:'monospace',textShadow:'0 0 20px #D4A85566'}}>{Math.round(Math.min(100,score))}</span>
        <span style={{fontSize:10,color:'#6A5A3A',fontFamily:'monospace',letterSpacing:'0.16em'}}>% CONNECTION</span>
      </div>
    </div>
  );
}

function StageBar({ score }) {
  const stage=getStage(score);
  return (
    <div style={{position:'absolute',bottom:28,left:'50%',transform:'translateX(-50%)',display:'flex',alignItems:'center',
      gap:0,background:'rgba(7,5,3,0.80)',backdropFilter:'blur(10px)',border:'1px solid #221A10',
      borderRadius:40,padding:'10px 28px',boxShadow:'0 4px 24px rgba(0,0,0,0.55)'}}>
      {STAGE_NAMES.map((name,i)=>{
        const reached=score>=STAGE_SCORES[i], current=stage===i;
        return (
          <React.Fragment key={name}>
            <div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:5}}>
              <div style={{width:current?12:8,height:current?12:8,borderRadius:'50%',background:current?'#D4A855':reached?'#5A4030':'#1E1810',boxShadow:current?'0 0 12px #D4A855BB':'none',transition:'all 0.6s ease'}}/>
              <span style={{fontSize:8,fontFamily:'monospace',letterSpacing:'0.14em',color:current?'#C8A044':reached?'#4A3828':'#1E1810',textTransform:'uppercase',transition:'color 0.6s ease'}}>{name}</span>
            </div>
            {i<STAGE_NAMES.length-1&&<div style={{width:28,height:1,margin:'0 4px',marginBottom:12,background:reached&&score>=STAGE_SCORES[i+1]?'#5A4030':'#1E1810',transition:'background 0.4s ease'}}/>}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function RepairBtn({ blockStates, onRepair }) {
  const hasCracked=[...CRACKED_IDS].some(id=>blockStates[id]==='cracked');
  const isHealing=[...CRACKED_IDS].some(id=>blockStates[id]==='repairing');
  const allHealed=!hasCracked&&!isHealing&&[...CRACKED_IDS].some(id=>blockStates[id]==='repaired');
  return (
    <button id="repair-btn" onClick={onRepair} disabled={!hasCracked||isHealing} style={{
      position:'absolute',bottom:90,right:28,padding:'11px 22px',
      background:allHealed?'linear-gradient(135deg,#3A2800,#6A4E00)':'rgba(14,10,6,0.88)',
      border:`1px solid ${allHealed?'#D4AF37':hasCracked?'#5A3828':'#221A10'}`,borderRadius:8,
      color:allHealed?'#FFD700':hasCracked?'#C8A870':'#3A2A18',
      fontFamily:'monospace',fontSize:10,letterSpacing:'0.2em',textTransform:'uppercase',
      cursor:hasCracked&&!isHealing?'pointer':'default',transition:'all 0.5s ease',
      boxShadow:allHealed?'0 0 22px #D4AF3748':'none',backdropFilter:'blur(6px)',
    }}>
      {allHealed?'✦ Kintsugi Complete':isHealing?'◌ Healing…':hasCracked?'⬡ Both Accept · Repair':'⬡ Repair'}
    </button>
  );
}

/* Stage achievement copy */
const STAGE_PEEK = [
  { emoji:'🪵', label:'Hut',     sub:'Where it all started', milestones:['First shelter built','Bamboo & wicker walls','Kept the rain out'] },
  { emoji:'🏡', label:'Cottage', sub:'First real walls',      milestones:['Stone foundations laid','Plaster & timber frame','A place to call home'] },
  { emoji:'🏠', label:'House',   sub:'Solid and lasting',     milestones:['Fired brick walls','Slate roof added','Chimney & windows'] },
  { emoji:'🏰', label:'Manor',   sub:'Standing strong',       milestones:['Tower foundations','Stone battlements','The view from the top'] },
  { emoji:'🏯', label:'Castle',  sub:'A fortress of memories',milestones:['Second tower risen','Full battlements','Castle complete'] },
];

/* ═══ STAGE PEEK PANEL ═══════════════════════════════════════════════════ */
function PeekPanel({ completedStages, peekStage, onSelect, onClose }) {
  if (completedStages.length === 0) return null;
  const sel = peekStage !== null ? STAGE_PEEK[peekStage] : null;
  return (
    <div style={{
      position:'absolute', top:24, right:28,
      display:'flex', flexDirection:'column', alignItems:'flex-end', gap:10,
      fontFamily:'"Outfit",sans-serif',
    }}>
      {/* Tab row */}
      <div style={{
        display:'flex', gap:6, background:'rgba(7,5,3,0.88)',
        border:'1px solid #221A10', borderRadius:40, padding:'8px 14px',
        backdropFilter:'blur(12px)', boxShadow:'0 4px 20px rgba(0,0,0,0.5)',
      }}>
        {peekStage !== null && (
          <button id="peek-close" onClick={onClose} style={{
            background:'none', border:'none', color:'#5A4428', cursor:'pointer',
            fontFamily:'monospace', fontSize:9, letterSpacing:'0.18em', padding:'4px 8px',
            transition:'color 0.3s',
          }} onMouseEnter={e=>e.target.style.color='#C8A044'}
             onMouseLeave={e=>e.target.style.color='#5A4428'}>
            ✕
          </button>
        )}
        {completedStages.map(si => {
          const sp = STAGE_PEEK[si];
          const active = peekStage === si;
          return (
            <button key={si} id={`peek-stage-${si}`} onClick={()=>onSelect(si)} style={{
              background: active ? 'rgba(200,160,68,0.18)' : 'none',
              border: active ? '1px solid #C8A04466' : '1px solid transparent',
              borderRadius:24, padding:'5px 14px',
              color: active ? '#D4A844' : '#5A4428',
              fontFamily:'monospace', fontSize:9, letterSpacing:'0.2em', textTransform:'uppercase',
              cursor:'pointer', transition:'all 0.3s ease',
            }}>
              {sp.emoji} {sp.label}
            </button>
          );
        })}
        {peekStage === null && (
          <span style={{
            fontSize:9, color:'#3A2818', fontFamily:'monospace',
            letterSpacing:'0.2em', padding:'5px 4px', userSelect:'none',
          }}>◎ PEEK AT PAST</span>
        )}
      </div>

      {/* Achievement card for selected stage */}
      {sel && (
        <div style={{
          background:'rgba(7,5,3,0.92)', border:'1px solid #2A1A08',
          borderRadius:12, padding:'16px 20px', maxWidth:220,
          backdropFilter:'blur(14px)', boxShadow:'0 8px 32px rgba(0,0,0,0.6)',
        }}>
          <div style={{fontSize:28, marginBottom:6}}>{sel.emoji}</div>
          <div style={{fontSize:15, fontWeight:700, color:'#F0E4CC', marginBottom:2}}>{sel.label}</div>
          <div style={{fontSize:11, color:'#7A6040', fontStyle:'italic', marginBottom:12}}>{sel.sub}</div>
          <div style={{display:'flex', flexDirection:'column', gap:6}}>
            {sel.milestones.map((m,i) => (
              <div key={i} style={{display:'flex', alignItems:'center', gap:8}}>
                <div style={{width:5, height:5, borderRadius:'50%', background:'#C8A044', flexShrink:0}} />
                <span style={{fontSize:10, color:'#A89060', lineHeight:1.4}}>{m}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══ VIEWPORT ═══════════════════════════════════════════════════════════ */
export default function BranchingPOCViewport() {
  const [blockStates,setBlockStates]=useState(()=>Object.fromEntries(SLOTS.map(s=>[s.id,'pending'])));
  const [score,setScore]=useState(0);
  const [peekStage,setPeekStage]=useState(null); // null=normal, 0=hut, 1=cottage, 2=house...
  const fireDustRef=useRef(null), flashRef=useRef(null);
  const queueRef=useRef([]), busyRef=useRef(false);
  const prevStageRef=useRef(0);

  const setOne=useCallback((id,s)=>setBlockStates(p=>({...p,[id]:s})),[]);

  // Retire old-stage blocks when stage advances — permanent blocks always stay
  const retireStage=useCallback((oldSi)=>{
    setBlockStates(prev=>{
      const next={...prev};
      SLOTS.forEach(slot=>{
        if (
          slot.si===oldSi &&
          !slot.permanent &&
          slot.retirable &&
          ['placed','cracked','repaired'].includes(prev[slot.id])
        ) {
          next[slot.id]='dormant';
        }
      });
      return next;
    });
  },[]);

  // How long to pause and admire a completed stage before the next one starts
  const STAGE_PAUSE_MS = 4200;

  const pop=useCallback(()=>{
    if (busyRef.current||!queueRef.current.length) return;
    busyRef.current=true;
    const id=queueRef.current.shift();
    const slot=SLOTS.find(s=>s.id===id);
    const newScore=slot.sc;
    setScore(newScore);

    // Check stage advance
    const newStage=getStage(newScore);
    if (newStage>prevStageRef.current) {
      const oldSi=prevStageRef.current;
      prevStageRef.current=newStage;
      retireStage(oldSi); // immediate — no old-stage overlap with new stage blocks
    }

    setOne(id,'ghost');
    setTimeout(()=>setOne(id,'falling'),GHOST_MS);
    setTimeout(()=>{
      setOne(id,'settling');
      fireDustRef.current?.(slot.pos);
      flashRef.current?.(slot.pos);
    },GHOST_MS+FALL_MS);
    setTimeout(()=>{
      setOne(id,CRACKED_IDS.has(id)?'cracked':'placed');
      busyRef.current=false;

      // Detect if this was the LAST block of its stage
      // → next queued block belongs to a later stage → pause to admire the completed structure
      const nextId = queueRef.current[0];
      const nextSlot = nextId !== undefined ? SLOTS.find(s=>s.id===nextId) : null;
      const isStageComplete = nextSlot && getStage(nextSlot.sc) > getStage(newScore);
      const delay = isStageComplete ? STAGE_PAUSE_MS : GAP_MS;

      setTimeout(pop, delay);
    },GHOST_MS+FALL_MS+SETTLE_MS);
  },[setOne,retireStage]);

  useEffect(()=>{
    queueRef.current=SLOTS.filter(s=>s.sc<=POC_SCORE).sort((a,b)=>a.sc-b.sc).map(s=>s.id);
    const t=setTimeout(pop,900);
    return ()=>clearTimeout(t);
  },[pop]);

  const repair=useCallback(()=>{
    CRACKED_IDS.forEach(id=>{
      if (blockStates[id]!=='cracked') return;
      setOne(id,'repairing');
      setTimeout(()=>setOne(id,'repaired'),2600);
    });
  },[blockStates,setOne]);

  const stage=getStage(score);

  // Stages that are fully completed (all their non-pending blocks are placed/dormant)
  const completedStages = useMemo(() => {
    const result = [];
    for (let si = 0; si < stage; si++) {
      const stageSlots = SLOTS.filter(s => s.si === si);
      const allDone = stageSlots.every(s =>
        ['placed','cracked','repaired','dormant'].includes(blockStates[s.id])
      );
      if (allDone && stageSlots.length > 0) result.push(si);
    }
    return result;
  }, [blockStates, stage]);

  return (
    <div style={{width:'100vw',height:'100vh',background:'#060504',position:'relative',overflow:'hidden'}}>
      <style>{`@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');*{box-sizing:border-box;}button{outline:none;font-family:monospace;}`}</style>
      <Canvas shadows camera={{position:[5.2,4.6,11.8],fov:46}} style={{width:'100%',height:'100%'}} gl={{antialias:true}}>
        <color attach="background" args={['#060504']} />
        <fogExp2 attach="fog" color="#060504" density={0.015} />
        <JourneyScene
          blockStates={blockStates}
          fireDustRef={fireDustRef}
          flashRef={flashRef}
          score={score}
          peekStage={peekStage}
        />
        <OrbitControls enableZoom enablePan={false} enableRotate autoRotate autoRotateSpeed={0.26}
          minDistance={4} maxDistance={22} minPolarAngle={0.18} maxPolarAngle={Math.PI*0.46} target={[0,1.4,0]} />
      </Canvas>
      <TitleHUD score={score} stage={stage} />
      <PeekPanel
        completedStages={completedStages}
        peekStage={peekStage}
        onSelect={si => setPeekStage(prev => prev === si ? null : si)}
        onClose={() => setPeekStage(null)}
      />
      <RepairBtn blockStates={blockStates} onRepair={repair} />
      <StageBar score={score} />
      <div style={{position:'absolute',inset:0,pointerEvents:'none',background:'radial-gradient(ellipse 82% 82% at 50% 52%,transparent 46%,rgba(3,2,1,0.82) 100%)'}}/>
    </div>
  );
}
