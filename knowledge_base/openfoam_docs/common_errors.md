# Common OpenFOAM Errors — Causes and Fixes

## Error 1: Floating Point Exception (SIGFPE)

**Symptom:**
```
[0] Floating point exception (core dumped)
```
or residuals suddenly jump to NaN/Inf.

**Causes:**
- Division by zero (zero-area face, collapsed cell)
- Invalid mesh: negative-volume cells
- Time step too large (CFL > 1 for explicit schemes)
- Boundary condition mismatch

**Fixes:**
1. Run `checkMesh` — look for negative volume cells or high non-orthogonality
2. Reduce `deltaT` or lower `maxCo` to 0.3
3. Check BCs for missing patches or conflicting types

---

## Error 2: Maximum Number of Iterations Exceeded

**Symptom:**
```
PCG: Solving for p_rgh, Initial residual = 0.5, Final residual = 0.049,
No Iterations 1000
DICPCG: Solving for p_rgh ...
Maximum number of iterations 1000 exceeded
```

**Causes:**
- Linear solver tolerance too tight for current mesh quality
- Non-orthogonality too high (> 70°) — the off-diagonal correction dominates
- Missing pressure reference cell (closed domain)
- Inconsistent BCs

**Fixes:**
1. Add `pRefCell 0; pRefValue 0;` inside PIMPLE/SIMPLE if domain is closed
2. Add `nNonOrthogonalCorrectors 2` to explicitly correct for mesh non-orthogonality
3. Switch solver: `PCG → GAMG` or vice versa
4. Relax tolerance: `relTol 0.1` instead of `relTol 0`

---

## Error 3: Continuity Error Too High

**Symptom:**
```
time step continuity errors : sum local = 1.23e+02, global = 4.5e+01
```
(values > 1e-3 are concerning; > 1 indicates serious mass imbalance)

**Causes:**
- Mesh non-orthogonality without correction
- Incompatible velocity/pressure BCs
- `adjustTimeStep` with very large jumps

**Fixes:**
1. Increase `nNonOrthogonalCorrectors` (1–3)
2. Verify inlet/outlet area × velocity matches physically expected flow rate
3. Run `checkMesh` and repair mesh if non-orthogonality > 70°

---

## Error 4: Negative Volume Cells

**Symptom:**
```
FOAM FATAL ERROR: face 1234 area = -0.00123
```
or `checkMesh` reports: `FAILED: Failed 5 mesh checks.`

**Causes:**
- Bad blockMeshDict vertex ordering (wrong chirality)
- Mesh refinement collapsing cells
- snappyHexMesh over-aggressive snapping

**Fixes:**
1. In blockMeshDict: vertices must follow right-hand rule: bottom-face clockwise,
   top-face counter-clockwise as seen from outside
2. Increase `nSmoothPatch` and `nRelaxIter` in snappyHexMesh
3. Check `mergePatchPairs` for mismatched patch areas

---

## Error 5: Courant Number Too High

**Symptom:**
```
Courant Number mean: 0.24 max: 8.73
```
Simulation usually diverges shortly after.

**Causes:**
- `deltaT` too large for mesh resolution
- Local mesh refinement creating very small cells
- Flow accelerating through a narrow passage

**Fixes:**
1. Enable adaptive time-stepping: `adjustTimeStep yes; maxCo 0.5;`
2. Add local mesh refinement only where needed — avoid large aspect ratio jumps
3. Set `maxDeltaT` as an upper bound

---

## Error 6: Alpha Outside [0,1] Bounds

**Symptom:**
```
Phase-1 volume fraction = 0.048  Min(alpha.water) = -0.032  Max(alpha.water) = 1.042
```

**Causes:**
- `maxCo` or `maxAlphaCo` too high
- Wrong divSchemes for alpha (not using vanLeer or MULES)
- Coarse mesh at interface

**Fixes:**
1. Reduce `maxCo` to 0.3–0.5 and `maxAlphaCo` to 0.3–0.5
2. Use `div(phi,alpha) Gauss vanLeer;` in fvSchemes
3. Enable MULES correction: `MULESCorr yes;` in alpha field settings
4. Refine mesh near the free surface

---

## Error 7: Pressure Reference Cell Not Found

**Symptom:**
```
FOAM FATAL ERROR: No pressure reference cell set
```

**Cause:** Closed domain (no pressure outlet BC) without a pressure reference.

**Fix:**
```
PIMPLE  // or SIMPLE
{
    pRefCell    0;
    pRefValue   0;
}
```

---

## Error 8: Patch Not Found / Boundary Mismatch

**Symptom:**
```
FOAM FATAL ERROR: Cannot find patch "inlet" in polyMesh/boundary
```

**Causes:**
- Patch name in `0/` file doesn't match the mesh boundary
- blockMeshDict was modified after `0/` files were written

**Fix:**
Run `foamDictionary -entry "boundaryField" constant/polyMesh/boundary`
to see actual patch names, then update `0/` field files.

---

## Error 9: High Skewness Warning

**Symptom from checkMesh:**
```
Mesh OK. Maximum face skewness = 4.23 (limit is 4.0)
```

**Cause:** Cells are heavily skewed — common with unstructured tet meshes near
curved surfaces.

**Fix:**
1. Add `nNonOrthogonalCorrectors 1` to PIMPLE/SIMPLE
2. Use `snGradSchemes { default limited 0.5; }` instead of `corrected`
3. Re-mesh with smoother transition layers

---

## Error 10: Wrong Number of Entries in Field

**Symptom:**
```
FOAM FATAL IO ERROR: Wrong token type - expected word found on line 123
```

**Cause:** Manual edit of a field file left an inconsistent cell count.

**Fix:**
Delete the problematic time directory and rerun `setFields`.

---

## Error 11: Cannot Decompose Par

**Symptom:**
```
FOAM FATAL ERROR: Cannot open file "system/decomposeParDict"
```

**Fix:**
Create `system/decomposeParDict`:
```
method      scotch;    // or simple, hierarchical
numberOfSubdomains 4;
```

---

## Error 12: divergence(rhoPhi) — Compressible interFoam Error

**Symptom:**
```
FOAM FATAL ERROR: divergence(rhoPhi,U) not found in divSchemes
```

**Fix:** Add to `divSchemes`:
```
div(rhoPhi,U)    Gauss linearUpwind grad(U);
```

---

## Error 13: GAMG: No Valid Agglomeration Found

**Symptom:**
```
GAMG: No valid agglomeration for coarsest level
```

**Causes:**
- Very small mesh (< 100 cells) — GAMG needs sufficient cells to coarsen
- Single processor run on a very coarse block

**Fix:** Switch p_rgh solver to `PCG` with `DIC` preconditioner.

---

## Error 14: Illegal Triangular Face

**Symptom:**
```
face 5678 has fewer than 4 vertices
```

**Cause:** Degenerate face in blockMeshDict from coincident vertices.

**Fix:** Check for duplicate vertex coordinates in `blockMeshDict`.

---

## Error 15: setFields Fails Silently

**Symptom:** `setFields` runs without error, but `alpha.water` is all zeros.

**Causes:**
- Box coordinates in `setFieldsDict` don't overlap with mesh cells
- z-range does not include mesh z-extent (for 2D cases: use -1 to 1)

**Fix:**
```
box (0 0 -1) (0.4 0.6 1);   // z-range must span the 2D mesh thickness
```

---

## Error 16: Library Not Found

**Symptom:**
```
FOAM FATAL ERROR: cannot find library "libcompressibleRASModels.so"
```

**Fix:** Source the OpenFOAM environment:
```bash
source /opt/openfoam11/etc/bashrc
```

---

## Error 17: Equation of State: Negative Temperature

**Symptom (rhoPimpleFoam):**
```
FOAM FATAL ERROR: Temperature out of range (T < 0): min T = -234 K
```

**Causes:**
- Pressure/temperature BCs incompatible with chosen EOS
- Large initial transients in compressible solver

**Fix:**
1. Start from a physically reasonable initial condition (not uniform p=0, T=300)
2. Use pseudo-transient ramping: start with large `relaxationFactors` and tighten

---

## Error 18: Alpha Residual Not Converging (MULES)

**Symptom:** Alpha MULES outer iterations reach `nAlphaCorr` limit every step.

**Fix:**
```
nAlphaCorr      2;
nAlphaSubCycles 2;
cAlpha          1;
MULESCorr       yes;
nLimiterIter    5;    // increase limiter iterations
```

---

## Error 19: Turbulent Viscosity Ratio Exceeded

**Symptom:**
```
Turbulent viscosity limited to viscosity ratio of 1e5
```

**Causes:**
- k-ε or k-ω initialized with too high k and too low ε/ω
- Turbulent inlet BC giving unrealistic values

**Fix:**
- Set k ≈ 1.5(IU)² where I ≈ 0.05 for 5% turbulence intensity
- Set ω ≈ k^0.5 / (Cμ^0.25 · L) where L is turbulent length scale

---

## Error 20: checkMesh — Aspect Ratio Warning

**Symptom:**
```
Maximum aspect ratio = 1342.5
```

**Cause:** Highly stretched cells in the boundary layer or far field.

**Consequence:** Large discretisation error in high-gradient regions.

**Fix:**
1. For boundary layer resolution: target y+ ≈ 30 for wall functions, or y+ < 5
   for low-Re models
2. Use geometric grading (ratio 1.1–1.3 per layer) in blockMeshDict
3. Check that `simpleGrading` values match the physical gradient magnitude
