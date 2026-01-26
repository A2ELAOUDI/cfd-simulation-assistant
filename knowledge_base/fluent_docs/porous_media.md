# Porous Media in ANSYS Fluent

## Physical Model: Darcy-Forchheimer

Fluent adds a momentum sink S_i to the transport equation in porous zones:

```
S_i = -(μ/α · D_ij · u_j + ½·ρ·|U|·C_ij · u_j)
    = -(C1_ij · μ · u_j + C2_ij · ½·ρ·|U|·u_j)
```

Where:
- `C1_ij` = viscous resistance coefficient [1/m²] (Darcy term, dominates at low Re)
- `C2_ij` = inertial resistance coefficient [1/m] (Forchheimer term, dominates at high Re)
- `μ` = dynamic viscosity [Pa·s]
- `ρ` = density [kg/m³]
- `|U|` = velocity magnitude [m/s]

---

## Setting Up Porous Zones

### GUI Method (Cell Zone Conditions)
1. *Physics → Cell Zone Conditions → [your zone] → Porous Zone (check)*
2. Under **Fluid** tab → enable **Porous Zone**
3. Set direction vectors (principal flow direction)
4. Enter C1 (viscous) and C2 (inertial) resistance values per direction

### Calculating Resistance Coefficients from Pressure Drop Data

If you have experimental data: ΔP/L = f(U), fit to:
```
ΔP/L = C1 · μ · U + C2 · ½ · ρ · U²
```

For a granular bed (Ergun equation):
```
C1 = 150 · (1-ε)² / (ε³ · dp²)     [1/m²]
C2 = 3.5 · (1-ε) / (ε³ · dp)       [1/m]
```
where ε = bed void fraction [-], dp = particle diameter [m].

**Example (limestone bed, dp=2mm, ε=0.4):**
```
C1 = 150 × (0.6)² / (0.064 × 0.000004) = 150 × 0.36 / 2.56e-7 = 2.109e8 m⁻²
C2 = 3.5 × 0.6 / (0.064 × 0.002) = 2.1 / 1.28e-4 = 16406 m⁻¹
```

---

## Directional Anisotropy

For anisotropic media (different resistance in different directions):

| Direction | Description | Typical C1 ratio |
|-----------|-------------|-----------------|
| Axial (flow direction) | Through the bed | 1× |
| Transverse | Cross-flow | 10–100× (strongly blocked) |

Set large values in transverse directions to enforce 1D flow through the bed.

---

## UDF for Porous Media

Use `DEFINE_SOURCE` to implement custom momentum sinks:

```c
#include "udf.h"

/* Darcy-Forchheimer source term in x-direction */
DEFINE_SOURCE(porous_x_source, cell, thread, dS, eqn)
{
    real u = C_U(cell, thread);
    real rho = C_R(cell, thread);
    real mu = C_MU_L(cell, thread);
    real C1 = 2.109e8;   /* viscous resistance [1/m²] */
    real C2 = 16406.0;   /* inertial resistance [1/m] */

    real vel_mag = sqrt(C_U(cell,thread)*C_U(cell,thread)
                      + C_V(cell,thread)*C_V(cell,thread)
                      + C_W(cell,thread)*C_W(cell,thread));

    /* Linearisation for velocity: dS = -∂S/∂u */
    dS[eqn] = -(mu * C1 + 0.5 * rho * C2 * vel_mag);

    return -(mu * C1 * u + 0.5 * rho * C2 * vel_mag * u);
}
```

---

## Detecting and Debugging Porous Zone Issues

### Symptom: Flow bypasses porous zone
- **Cause:** Porous zone not assigned to the correct cell zone
- **Fix:** Verify in *Cell Zone Conditions* that the zone is enabled as porous

### Symptom: Pressure drop too high / simulation diverges
- **Cause:** C1 or C2 values too large
- **Fix:** Check units (1/m² for C1, 1/m for C2); compare to Ergun estimate

### Symptom: Species residuals plateau inside porous zone
- **Cause:** Very low velocity reduces convective flux; diffusion dominates
  with high numerical Peclet number
- **Fix:** Ensure species diffusivity D is physically correct; consider mesh
  refinement inside the porous zone

### Symptom: Temperature gradient inconsistent with expected heat transfer
- **Cause:** Porous zone uses fluid temperature (no solid energy equation)
- **Fix:** Enable *Porous Zone → Thermal Equilibrium* or use
  *Non-Equilibrium Thermal Model* for solid-fluid heat exchange

---

## Energy Source in Porous Zone via UDF

For dissolution reactions (e.g., CaCO3 + CO2 + H2O → Ca²⁺ + 2HCO₃⁻):

```c
DEFINE_SOURCE(dissolution_heat, cell, thread, dS, eqn)
{
    real R_diss;   /* dissolution rate [mol/m³/s] */
    real dH = -12400.0;  /* enthalpy of dissolution [J/mol], negative = exothermic */

    /* Get dissolution rate from UDM[1] (computed in DEFINE_ADJUST) */
    R_diss = C_UDMI(cell, thread, 1);

    dS[eqn] = 0.0;   /* energy source independent of T at first order */
    return R_diss * dH;   /* [W/m³] = [mol/m³/s] × [J/mol] */
}
```

---

## Checklist for Porous Media Setup

- [ ] Cell zone assigned as Porous Zone in Cell Zone Conditions
- [ ] Principal direction vectors are unit vectors summing to 1
- [ ] C1 and C2 in correct units (1/m² and 1/m)
- [ ] For packed beds: validate against Ergun equation
- [ ] Species transport enabled in all porous zones
- [ ] If UDF: check `dS[eqn]` is set; check units of return value
- [ ] Run with coarse under-relaxation first (URF = 0.3 for pressure)
