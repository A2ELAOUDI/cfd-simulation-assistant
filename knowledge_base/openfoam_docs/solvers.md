# OpenFOAM Solvers Guide

## Overview

OpenFOAM solvers are selected in `system/controlDict` via the `application`
keyword. Choosing the wrong solver is the most common setup error — the solver
must match the physics (compressible vs incompressible, steady vs transient,
single vs multiphase).

---

## interFoam

**Type:** Transient, incompressible, multiphase (2 immiscible fluids)  
**Algorithm:** PIMPLE + MULES (Multidimensional Universal Limiter for Explicit
Solution)  
**Interface tracking:** Volume of Fluid (VOF)

### Use cases
- Dam-break and wave propagation
- Tank filling/emptying
- Ship hydrodynamics (free surface)
- Slug flow in pipes
- Coastal flooding

### Key settings (controlDict)
```
application     interFoam;
adjustTimeStep  yes;
maxCo           0.5;      // interface Courant limit (critical!)
maxAlphaCo      0.5;      // VOF-specific Courant limit
```

### Key settings (fvSchemes)
```
div(phi,alpha)     Gauss vanLeer;     // VOF advection (bounded)
div(phirb,alpha)   Gauss linear;      // interface compression
div(rhoPhi,U)      Gauss linearUpwind grad(U);
```

### Pitfalls
- maxCo > 0.5 causes interface smearing and α outside [0,1]
- GAMG for p_rgh can stall near water-air interfaces; prefer PCG+DIC
- `nAlphaSubCycles` > 1 sharpens interface but increases cost

---

## simpleFoam

**Type:** Steady-state, incompressible, single-phase  
**Algorithm:** SIMPLE (Semi-Implicit Method for Pressure-Linked Equations)

### Use cases
- Internal aerodynamics (duct flow, HVAC)
- External aerodynamics at low speed
- Pump and turbine steady-state performance
- Any isothermal incompressible flow where transients don't matter

### Key settings (fvSolution)
```
SIMPLE
{
    nNonOrthogonalCorrectors 0;
    residualControl
    {
        p       1e-4;
        U       1e-4;
        "(k|epsilon|omega)" 1e-4;
    }
}
relaxationFactors
{
    fields  { p 0.3; }
    equations { U 0.7; k 0.7; epsilon 0.7; }
}
```

### Pitfalls
- Under-relaxation too high → oscillations; too low → slow convergence
- SIMPLE does not conserve mass exactly per iteration (unlike PISO)
- Not valid for transient phenomena — use pimpleFoam instead

---

## pimpleFoam

**Type:** Transient, incompressible, single-phase  
**Algorithm:** PIMPLE (merged PISO + SIMPLE outer loops)

### Use cases
- Time-accurate turbulent flow (LES, DES, k-ω SST unsteady)
- Vortex shedding, flow instabilities
- Acoustic simulations (aeroacoustics)
- Valve and pump transient operation

### Key settings (fvSolution)
```
PIMPLE
{
    nOuterCorrectors        2;   // SIMPLE-like outer iterations
    nCorrectors             2;   // PISO inner pressure corrections
    nNonOrthogonalCorrectors 1;
    pRefCell                0;   // required for closed domains
    pRefValue               0;
}
```

### nOuterCorrectors guidance
| Flow | nOuterCorrectors |
|------|-----------------|
| CFL < 1, smooth mesh | 1 (= pure PISO) |
| CFL 1–5, turbulence | 2–3 |
| Large time steps | 3–5 |

### Pitfalls
- nOuterCorrectors = 1 with large deltaT → poor coupling between U and p
- Large Co numbers without outer iterations → divergence

---

## rhoPimpleFoam

**Type:** Transient, compressible (density-based), single-phase  
**Algorithm:** PIMPLE for compressible flow

### Use cases
- High-speed aerodynamics (Ma > 0.3)
- Gas turbine combustor flows
- Pressure relief valves
- Shock-containing flows (with appropriate schemes)

### Key differences from pimpleFoam
- Solves for density ρ (from equation of state) instead of treating it as constant
- Requires `thermophysicalProperties` in `constant/`
- `p` is the total pressure; `p_rgh` is not used

### Pitfalls
- Do NOT use for incompressible flows — numerical diffusion of density creates
  fictitious compressibility effects
- Requires `linearUpwind` or `limitedLinear` schemes for stability

---

## buoyantPimpleFoam / buoyantSimpleFoam

**Type:** Transient or steady, compressible-with-buoyancy  
**Use cases:** Natural convection, fire plumes, heated rooms, stratified flows

Key feature: uses `p_rgh = p - ρgh` to decouple hydrostatic pressure gradient,
improving convergence in buoyancy-dominated flows.

---

## reactingFoam

**Type:** Transient, compressible, multispecies, reacting  
**Use cases:** Combustion, catalytic converters, chemical reactors

Solves the full energy equation and species transport with reaction source terms.
Requires `chemistryProperties`, `combustionProperties` in `constant/`.

---

## Solver Selection Chart

```
Flow type?
├── Single phase, incompressible
│   ├── Steady state → simpleFoam
│   └── Transient    → pimpleFoam
├── Multiphase (VOF)
│   └── Transient    → interFoam
├── Compressible
│   ├── Steady state → rhoSimpleFoam
│   └── Transient    → rhoPimpleFoam
├── Buoyancy-driven
│   ├── Steady state → buoyantSimpleFoam
│   └── Transient    → buoyantPimpleFoam
└── Reacting flows   → reactingFoam / fireFoam
```
