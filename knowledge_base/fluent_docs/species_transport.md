# Species Transport in ANSYS Fluent

## Governing Equation

For species i in a mixture:

```
∂(ρYᵢ)/∂t + ∇·(ρUYᵢ) = ∇·(ρDᵢ ∇Yᵢ) + Sᵢ
```

Where:
- Yᵢ = mass fraction of species i [-]
- Dᵢ = diffusivity of species i in the mixture [m²/s]
- Sᵢ = volumetric source term [kg/(m³·s)]

In Fluent, Sᵢ is provided via `DEFINE_SOURCE`.

---

## Setting Up Species Transport

1. *Physics → Models → Species → Species Transport*
2. Define mixture material with all species
3. Set diffusivities per species (constant, polynomial, or kinetic theory)
4. Enable reactions if needed
5. Set BCs: inlet = fixed Yᵢ; outlet = zero gradient

---

## Calcocarbonic Equilibrium — Limestone Contactor

A limestone contactor for water remineralization involves:

**Overall reaction:**
```
CaCO₃(s) + CO₂(aq) + H₂O(l) → Ca²⁺(aq) + 2HCO₃⁻(aq)
```

**Equilibrium reactions in solution:**
```
CO₂ + H₂O ⇌ H₂CO₃            K₁ = 4.5×10⁻⁷   (CO₂ hydration)
H₂CO₃ ⇌ H⁺ + HCO₃⁻           Ka1 = 4.5×10⁻⁷
HCO₃⁻ ⇌ H⁺ + CO₃²⁻           Ka2 = 4.7×10⁻¹¹
CaCO₃ ⇌ Ca²⁺ + CO₃²⁻         Ksp = 3.3×10⁻⁹
CO₂(g) ↔ CO₂(aq)              KH = 3.4×10⁻² mol/(L·atm) [Henry's law]
```

**pH calculation from alkalinity and DIC:**
```
DIC = [CO₂*] + [HCO₃⁻] + [CO₃²⁻]
Alk = [HCO₃⁻] + 2[CO₃²⁻] + [OH⁻] - [H⁺]
pH = -log₁₀([H⁺])
```

Solving iteratively:
```python
# Simplified (ignoring OH⁻ and CO₃²⁻ at pH 6–8):
[H⁺] = Ka1 * [CO₂] / ([HCO₃⁻])
pH = pKa1 + log10([HCO₃⁻]/[CO₂])
```

### Modelling Strategy in Fluent

| Quantity | UDS/UDM | Notes |
|----------|---------|-------|
| dissolved CO₂ concentration | Species 0 (Y_CO2) | Source from dissolution UDF |
| Ca²⁺ concentration | Species 1 (Y_Ca) | Source proportional to dissolution |
| HCO₃⁻ concentration | Species 2 (Y_HCO3) | Source = 2 × dissolution |
| pH | UDM[0] | Computed in DEFINE_ADJUST |
| Dissolution rate R | UDM[1] | Stored for heat source UDF |

### CO₂ Dissolution Source Term

```c
DEFINE_SOURCE(co2_dissolution_source, cell, thread, dS, eqn)
{
    real Y_co2 = C_YI(cell, thread, 0);
    real pH = C_UDMI(cell, thread, 0);
    real T = C_T(cell, thread);

    /* Equilibrium CO2 concentration at current pH (simplified) */
    real Y_co2_eq = Y_co2_equilibrium(pH, T);

    /* Rate proportional to driving force */
    real k_diss = 0.01;   /* dissolution rate constant [1/s], fit to experiment */
    real source = -k_diss * (Y_co2 - Y_co2_eq);

    dS[eqn] = -k_diss;    /* linearisation */
    return source;         /* [kg/m³/s] */
}
```

---

## Common Convergence Issues in Species Transport

### 1. Species Residuals Plateau at 1e-4 — Not Converging

**This is a well-known issue in calcocarbonic and other stiff chemistry simulations.**

**Causes:**
- **Stiff source terms**: the dissolution rate dS/dY is large, making the
  species matrix ill-conditioned
- **pH-alkalinity feedback loop**: pH computed in DEFINE_ADJUST uses old Y values;
  the updated pH changes the source in the next iteration, creating a lag
- **Low velocity in porous zone**: convective transport < diffusive transport →
  species equation behaves like an elliptic PDE → slow convergence
- **Poor linearisation**: missing or wrong dS[eqn] prevents proper implicit update

**Fixes (in priority order):**
1. Reduce species under-relaxation factor to 0.2–0.3 (default is 1.0)
2. Ensure DEFINE_ADJUST (pH update) executes before species solvers
3. Set `dS[eqn] = -k_diss` correctly in DEFINE_SOURCE
4. Refine mesh in porous zone (reduce cell Peclet number Pe = U·Δx/D)
5. If Y_CO2 and Y_Ca are tightly coupled: use Coupled solver (not segregated)
6. Increase number of species sweeps per iteration

### 2. Species Mass Fraction Becomes Negative

**Cause:** Source term too large or wrong sign; or convection scheme not bounded.

**Fix:**
- Ensure species diffusivity D > 0 (check material properties)
- Clip source: `source = MAX(source, -Y_co2 * rho / dt)` (prevent Y < 0)
- Use `Bounded Central Differencing` scheme for species

### 3. Discontinuity at Zone Interface

**Cause:** Different mesh density across porous/fluid interface creates
artificial species flux.

**Fix:** Use `Interior` boundary (not wall) between zones; ensure conformal mesh.

---

## Henry's Law — Gas Absorption

For CO₂ absorption into water:

```
p_CO2 = KH · [CO₂]_aq
```

Where KH = 29.41 L·atm/mol at 25°C (decreases with temperature).

In Fluent VOF or multiphase: set mass transfer source using:

```c
real Y_co2_gas = C_YI(cell, thread_gas, 0);
real p_co2 = C_P(cell, thread) * Y_co2_gas;   /* partial pressure */
real c_co2_aq_eq = p_co2 / (KH * M_co2);      /* equilibrium concentration */
real transfer_rate = k_L * area_density * (c_co2_aq_eq - c_co2_aq_current);
```

---

## Checklist for Species Transport

- [ ] All species defined in mixture material
- [ ] Diffusivities set correctly (liquid diffusivities ~1e-9 m²/s for ions)
- [ ] `dS[eqn]` set in all DEFINE_SOURCE functions
- [ ] Under-relaxation factor ≤ 0.5 for stiff chemistry
- [ ] DEFINE_ADJUST called every iteration (not just at convergence check)
- [ ] Inlet BC: fixed Yᵢ; Outlet BC: zero gradient (outflowPressure or outflow)
- [ ] Initial field: physically reasonable values (not zero for all species)
