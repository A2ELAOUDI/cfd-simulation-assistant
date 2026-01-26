# ANSYS Fluent — Limestone Contactor Simulation Setup

## Physical Problem

Simulation of a limestone contactor for drinking water remineralization.
Desalinated water (from reverse osmosis) is enriched with CO₂ and passed through
a packed bed of limestone (CaCO₃) pellets. The dissolution reaction raises pH,
hardness (Ca²⁺), and alkalinity (HCO₃⁻) to drinking water standards.

**Target output water quality:**
- pH: 7.5 – 8.5
- Ca²⁺: 40 – 80 mg/L
- Alkalinity (as CaCO₃): 100 – 150 mg/L

## Geometry

- Cylindrical contactor: D = 1.2 m, H = 2.5 m
- Inlet: bottom face (upflow configuration)
- Outlet: top face
- Porous zone: full cylinder (packed limestone, dp = 2 mm, ε = 0.40)
- 3D structured mesh: 12,500 cells

## Models Enabled

| Model | Settings |
|-------|---------|
| Flow | Steady-state, laminar (Re_pore ≈ 0.3) |
| Species transport | 3 species: CO₂(aq), Ca²⁺, HCO₃⁻ |
| Porous media | Darcy-Forchheimer (C1=2.1e8, C2=16400) |
| Energy | Isothermal (T = 15°C) |
| UDFs | 4 UDFs: CO2 source, Ca dissolution, HCO3 source, pH adjust |

## UDFs Loaded

1. `co2_dissolution_source`: removes CO₂ from solution proportional to (Y_CO2 - Y_CO2_eq)
2. `ca_dissolution_source`: adds Ca²⁺ from limestone dissolution
3. `hco3_production_source`: adds HCO₃⁻ at 2× molar ratio to Ca²⁺
4. `compute_pH`: DEFINE_ADJUST computing cell pH from Y_CO2 and storing in UDM[0]

## Boundary Conditions

| Boundary | Condition |
|----------|-----------|
| Inlet velocity | 0.003 m/s (upward) |
| Inlet CO₂ | Y_CO2 = 0.022 kg/kg (saturation at 5 bar CO₂ injection) |
| Inlet Ca²⁺ | Y_Ca = 0.0001 kg/kg (residual from RO permeate) |
| Inlet HCO₃⁻ | Y_HCO3 = 0.00012 kg/kg |
| Outlet | Pressure outlet, zero gradient for all scalars |
| Wall | No-slip, zero flux (adiabatic) |

## Convergence Target

Residuals < 1e-6 for all equations. Under-relaxation: p=0.3, U=0.7, species=1.0 (default).

## Known Issue

Species residuals (CO₂, Ca²⁺, HCO₃⁻) plateau at ~1e-4 after ~300 iterations.
Continuity and velocity converge to < 1e-6, but species remain stalled.
See `convergence_log.txt` for the detailed residual history.
