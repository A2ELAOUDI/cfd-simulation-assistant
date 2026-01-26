# OpenFOAM fvSchemes Guide

`system/fvSchemes` controls how spatial and temporal derivatives are
discretised. Poor scheme choices cause numerical diffusion, oscillations,
unboundedness, or divergence.

---

## ddtSchemes — Time Discretisation

```
ddtSchemes
{
    default     Euler;
}
```

| Scheme | Order | Notes |
|--------|-------|-------|
| `Euler` | 1st | Stable, dissipative. Default for most cases. |
| `backward` | 2nd | Less dissipative, may oscillate. Use with small Δt. |
| `CrankNicolson 0.9` | ~2nd | Blended CN (0=Euler, 1=pure CN). 0.9 recommended for LES. |
| `steadyState` | N/A | Steady-state solver (simpleFoam, rhoSimpleFoam). |
| `localEuler` | 1st | Local time-stepping for pseudo-transient acceleration. |

**Best practices:**
- interFoam: use `Euler` — `backward` can cause α to go out of [0,1]
- pimpleFoam LES: use `CrankNicolson 0.9` with Co < 0.5
- simpleFoam: always `steadyState`

---

## gradSchemes — Gradient Computation

```
gradSchemes
{
    default         Gauss linear;
    grad(U)         Gauss linear;
}
```

| Scheme | Accuracy | Notes |
|--------|----------|-------|
| `Gauss linear` | 2nd order | Standard. Requires good mesh quality. |
| `leastSquares` | 2nd order | Better on non-orthogonal meshes. Slightly more expensive. |
| `Gauss linear corrected` | 2nd order | With explicit non-orthogonal correction. |
| `cellLimited Gauss linear 1` | ~2nd | Gradient limiting for bounded fields. Use for k, ε, ω. |

**Best practices:**
- On hex meshes: `Gauss linear`
- On polyhedral or tetrahedral meshes: `leastSquares` or `Gauss linear corrected`
- For turbulence fields: `cellLimited Gauss linear 1` prevents negative k

---

## divSchemes — Divergence (Convection) Terms

This is the most impactful choice for accuracy vs stability.

```
divSchemes
{
    default             none;            // forces explicit definition of each term
    div(phi,U)          Gauss linearUpwind grad(U);
    div(phi,k)          Gauss upwind;
    div(phi,epsilon)    Gauss upwind;
    div(phi,alpha)      Gauss vanLeer;
    div(phirb,alpha)    Gauss linear;
}
```

### Upwind schemes (bounded, dissipative)

| Scheme | Order | Notes |
|--------|-------|-------|
| `Gauss upwind` | 1st | Most stable. High numerical diffusion. Use when boundedness matters more than accuracy. |
| `Gauss linearUpwind grad(phi)` | 2nd | Less diffusive. Good balance for RANS. |

### Central / linear schemes (accurate, may oscillate)

| Scheme | Order | Notes |
|--------|-------|-------|
| `Gauss linear` | 2nd | Unbounded! Use only for diffusion terms. |
| `Gauss LUST` | ~2.5 | Blended linear-upwind. Good for LES. |

### Bounded schemes for scalars in [0,1]

| Scheme | Notes |
|--------|-------|
| `Gauss vanLeer` | TVD limiter. Standard for VOF α in interFoam. |
| `Gauss MUSCL` | Higher-order TVD. Sharper than vanLeer. |
| `Gauss limitedLinear 1` | Flux limiter, value 1 = fully limited. |
| `Gauss limitedLinear01 1` | Limiter for scalars in [0,1]. Prevents overshoot. |

### Reynolds stress / viscous terms

```
div(((rho*nuEff)*dev2(T(grad(U)))))   Gauss linear;
```
Always use `Gauss linear` for viscous stress divergence — it is already smooth
and does not need limiting.

**Best practices by solver:**

| Solver | U convection | Scalar convection |
|--------|-------------|-------------------|
| simpleFoam | `linearUpwind grad(U)` | `upwind` |
| pimpleFoam RANS | `linearUpwind grad(U)` | `limitedLinear 1` |
| pimpleFoam LES | `LUST grad(U)` | `limitedLinear 1` |
| interFoam | `linearUpwind grad(U)` | `vanLeer` for α |

---

## laplacianSchemes — Diffusion Terms

```
laplacianSchemes
{
    default     Gauss linear corrected;
}
```

| Scheme | Notes |
|--------|-------|
| `Gauss linear corrected` | 2nd order with full non-orthogonal correction. Standard. |
| `Gauss linear limited 0.333` | Partial correction. Use when non-orthogonality > 70°. |
| `Gauss linear uncorrected` | No correction. Only for orthogonal meshes. |

**Important:** The correction term `corrected` adds a cross-diffusion flux that
can cause divergence on very poor meshes (non-orthogonality > 85°). Use
`limited 0.5` as a compromise.

---

## snGradSchemes — Surface-normal Gradients

Used internally for the non-orthogonal correction in laplacianSchemes.

```
snGradSchemes
{
    default     corrected;
}
```

Match to laplacianSchemes: `corrected` ↔ `corrected`, `limited N` ↔ `limited N`.

---

## interpolationSchemes

```
interpolationSchemes
{
    default     linear;
}
```

`linear` is almost always correct. Only change if advised by solver documentation.

---

## Common fvSchemes Mistakes

| Mistake | Consequence | Fix |
|---------|------------|-----|
| Using `Gauss linear` for `div(phi,U)` | Unbounded U, eventual divergence | Switch to `linearUpwind` or `upwind` |
| Using `Gauss upwind` for LES | Excessive numerical diffusion kills turbulent structures | Use `LUST` or `linearUpwind` |
| No explicit definition, relying on `default none` | Runtime error: scheme not found | Add explicit entry for each convective term |
| `Gauss linear corrected` on mesh with non-orthogonality > 85° | Divergence | Use `Gauss linear limited 0.5` |
| Wrong scheme for VOF α (e.g., `Gauss linear`) | α goes outside [0,1] | Use `Gauss vanLeer` |
