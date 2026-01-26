# OpenFOAM Boundary Conditions

Boundary conditions (BCs) are defined in the `0/` directory, one file per
field. The `boundaryField` dict maps each patch name to a BC type and value.

---

## Velocity (U) Boundary Conditions

### fixedValue
```
type    fixedValue;
value   uniform (1.0 0 0);   // or nonuniform for mapped profiles
```
Prescribes the velocity at the boundary (Dirichlet). Use at inlets.

### noSlip
```
type    noSlip;
```
Shorthand for `fixedValue uniform (0 0 0)`. Use on solid walls.

### slip
```
type    slip;
```
Zero normal velocity, zero shear stress. Use for symmetry planes or frictionless
walls.

### pressureInletOutletVelocity
```
type        pressureInletOutletVelocity;
value       uniform (0 0 0);
```
Calculates velocity from the pressure gradient at the boundary. Used at
**outlets with pressure BC on p**. Adjusts direction based on flow — inflow
uses zero gradient, outflow uses the local velocity. Essential for interFoam
open boundaries.

### inletOutlet
```
type        inletOutlet;
inletValue  uniform (0 0 0);
value       uniform (0 0 0);
```
Acts as `zeroGradient` when outflow, switches to `fixedValue inletValue` when
backflow occurs. Used to prevent spurious reverse flow at outlets.

### fixedFluxPressure (for U — not a BC type)
Not applied to U directly; used in `p_rgh`. See pressure section.

---

## Pressure (p / p_rgh) Boundary Conditions

### totalPressure
```
type    totalPressure;
p0      uniform 101325;      // stagnation pressure [Pa]
```
Maintains p₀ = p + ½ρ|U|² = const. Use at inlet if total pressure is known.

### fixedFluxPressure
```
type        fixedFluxPressure;
gradient    uniform 0;
value       uniform 0;
```
Adjusts the pressure gradient to ensure zero-flux through the wall. Required at
**all solid wall patches** when `p_rgh` is used (interFoam, buoyantFoam).

### zeroGradient
```
type    zeroGradient;
```
∂p/∂n = 0. Use at inlets when prescribing fixed velocity. Also at walls when
not using `p_rgh`.

### outlet with fixed pressure
```
type    fixedValue;
value   uniform 0;           // gauge pressure = 0 (reference)
```
Use at outlets to set the reference pressure level.

---

## Scalar fields (α, T, k, ε, ω, species)

### zeroGradient
```
type    zeroGradient;
```
∂φ/∂n = 0. Most common at outlets and walls for passive scalars.

### inletOutlet (for alpha.water)
```
type        inletOutlet;
inletValue  uniform 0;      // air at atmosphere
value       uniform 0;
```
Standard BC for the VOF fraction at open top boundaries.

### fixedValue (for temperature or species)
```
type    fixedValue;
value   uniform 300;         // [K] or mass fraction
```
Dirichlet. Use at inlets where the inlet temperature or composition is known.

### turbulentIntensityKineticEnergyInlet
```
type                turbulentIntensityKineticEnergyInlet;
intensity           0.05;    // 5% turbulence intensity
value               uniform 0.01;
```
Calculates k from turbulence intensity and velocity magnitude. Use for k at
inlets.

### kqRWallFunction
```
type    kqRWallFunction;
value   uniform 0;
```
Wall function for turbulent kinetic energy. Required at walls when using k-ε
or k-ω.

### nutkWallFunction
```
type    nutkWallFunction;
value   uniform 0;
```
Wall function for turbulent viscosity νt based on wall distance. Required at
walls for turbulence models.

### epsilonWallFunction
```
type    epsilonWallFunction;
value   uniform 200;
```
Wall function for dissipation rate ε. Required at walls for k-ε models.

### omegaWallFunction
```
type    omegaWallFunction;
value   uniform 200;
```
Wall function for specific dissipation rate ω. Required at walls for k-ω SST.

---

## Symmetry and Cyclic

### symmetryPlane
```
type    symmetryPlane;
```
Mirror BC: normal component of vectors is reflected, scalars are continuous.
Use on symmetry planes to halve domain size.

### cyclic
```
type    cyclic;
```
Connects two matching patches periodically. Patch pairs must be defined with
`matchTolerance` in blockMeshDict. Use for periodic domains (channels, pipes).

### cyclicAMI
```
type    cyclicAMI;
```
Arbitrary Mesh Interface cyclic BC. Used for non-conformal periodic patches
(e.g., rotating machinery with moving mesh).

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `zeroGradient` on p at both inlet and outlet | One BC must be `fixedValue` to set the reference pressure level |
| Using `fixedValue` on U at outlet | Use `inletOutlet` or `pressureInletOutletVelocity` to allow backflow |
| Missing `fixedFluxPressure` at walls with `p_rgh` | Add `fixedFluxPressure` to all wall patches in the p_rgh file |
| Wall function BCs on turbulence for y+ < 5 | Either resolve boundary layer (use `kLowReWallFunction`) or refine mesh to reach y+ > 30 |
| `noSlip` at a symmetry plane | Use `symmetryPlane` or `slip` |
