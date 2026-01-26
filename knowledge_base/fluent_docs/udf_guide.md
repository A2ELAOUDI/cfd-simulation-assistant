# ANSYS Fluent UDF Guide

User-Defined Functions (UDFs) extend Fluent with custom physics, written in C
and compiled dynamically. They hook into Fluent's solver at specific points.

---

## Required Header

Every UDF file must begin with:
```c
#include "udf.h"
```
This provides access to all Fluent macros, data types, and thread handles.

---

## Core DEFINE_* Macros

### DEFINE_SOURCE — Custom Source Terms

Adds a volumetric source to any transport equation (momentum, species, energy).

```c
DEFINE_SOURCE(my_co2_source, cell, thread, dS, eqn)
{
    real source;
    real T = C_T(cell, thread);           // temperature [K]
    real p = C_P(cell, thread);           // pressure [Pa]
    real Y_co2 = C_YI(cell, thread, 0);  // CO2 mass fraction (species index 0)

    /* First-order linearisation (CRITICAL for convergence): */
    dS[eqn] = -k_diss;        // ∂S/∂φ — stabilises the species matrix
    /* If source is constant: dS[eqn] = 0.0; */

    source = -k_diss * Y_co2;  // first-order dissolution rate [kg/m³/s]
    return source;
}
```

**Key rule:** Always set `dS[eqn]` — the Jacobian of the source with respect to
the solved variable. Missing this causes slow convergence (solver cannot form
a proper linearised system).

**Sign convention:**
- Positive source → adds mass/momentum/energy to cell
- Negative source → removes it

### DEFINE_INIT — Initialization Hook

Runs once when `Initialize Solution` is clicked.

```c
DEFINE_INIT(my_init, domain)
{
    Thread *t;
    cell_t c;

    thread_loop_c(t, domain)
    {
        begin_c_loop(c, t)
        {
            C_UDMI(c, t, 0) = 0.0;      /* initialize UDM slot 0 */
            C_T(c, t) = 298.15;         /* override temperature */
        }
        end_c_loop(c, t)
    }
}
```

### DEFINE_ADJUST — Per-Iteration Adjustment

Runs at the beginning of every iteration (before solvers are called).
Use for:
- Computing derived quantities (pH from species concentrations)
- Updating UDM values
- Checking convergence of custom variables

```c
DEFINE_ADJUST(compute_pH, domain)
{
    Thread *t;
    cell_t c;
    real Y_co2, Y_ca, pH;

    thread_loop_c(t, domain)
    {
        begin_c_loop(c, t)
        {
            Y_co2 = C_YI(c, t, 0);
            Y_ca  = C_YI(c, t, 1);

            /* Simplified calcocarbonic equilibrium */
            pH = 6.3 + log10(1.0 / (Y_co2 + 1e-10));

            C_UDMI(c, t, 0) = pH;   /* store pH in UDM[0] */
        }
        end_c_loop(c, t)
    }
}
```

### DEFINE_ON_DEMAND — User-Triggered Function

Registered as a function that the user can call manually from the GUI or TUI.

```c
DEFINE_ON_DEMAND(print_max_pH)
{
    Domain *domain = Get_Domain(1);
    Thread *t;
    cell_t c;
    real max_pH = -1e10;

    thread_loop_c(t, domain)
    {
        begin_c_loop(c, t)
        {
            max_pH = MAX(max_pH, C_UDMI(c, t, 0));
        }
        end_c_loop(c, t)
    }
    Message("Maximum pH = %g\n", max_pH);  /* parallel-safe output */
}
```

### DEFINE_PROFILE — Boundary Profile

Sets a spatially varying BC value.

```c
DEFINE_PROFILE(inlet_velocity_profile, thread, position)
{
    real x[ND_ND];
    real y, v_profile;
    face_t f;

    begin_f_loop(f, thread)
    {
        F_CENTROID(x, f, thread);
        y = x[1];   /* y-coordinate of face centroid */
        v_profile = 1.5 * (1.0 - (y/0.1)*(y/0.1));  /* parabolic profile */
        F_PROFILE(f, thread, position) = v_profile;
    }
    end_f_loop(f, thread)
}
```

---

## Cell and Face Data Access Macros

| Macro | Returns | Unit |
|-------|---------|------|
| `C_T(c, t)` | Temperature | K |
| `C_P(c, t)` | Static pressure | Pa |
| `C_R(c, t)` | Density | kg/m³ |
| `C_U(c, t)` | x-velocity | m/s |
| `C_V(c, t)` | y-velocity | m/s |
| `C_W(c, t)` | z-velocity | m/s |
| `C_YI(c, t, i)` | Species mass fraction index i | — |
| `C_K(c, t)` | Turbulent kinetic energy k | m²/s² |
| `C_D(c, t)` | Turbulent dissipation ε | m²/s³ |
| `C_MU_T(c, t)` | Turbulent viscosity μt | Pa·s |
| `C_VOLUME(c, t)` | Cell volume | m³ |
| `C_UDMI(c, t, i)` | User-defined memory slot i | user-defined |
| `C_UDSI(c, t, i)` | User-defined scalar i | user-defined |

---

## User-Defined Memory (UDM) and Scalars (UDS)

Fluent provides up to 500 UDM slots and 50 UDS equations.

**UDM** (User-Defined Memory): simple per-cell storage, no transport equation.
```c
C_UDMI(c, t, 0) = my_value;    /* write */
real v = C_UDMI(c, t, 0);      /* read  */
```
Enable in: *User Defined → User Defined Memory → Number of UDM = N*

**UDS** (User-Defined Scalar): full transport equation Dφ/Dt = S.
Requires a DEFINE_DIFFUSIVITY UDF and DEFINE_SOURCE for the source term.

---

## Parallel Computing Considerations

In parallel Fluent, UDFs run on all compute nodes simultaneously. Critical rules:

1. **File I/O**: only on node 0
```c
if (I_AM_NODE_ZERO) {
    FILE *fp = fopen("output.txt", "w");
    /* ... */
    fclose(fp);
}
PRF_GSYNC();   /* synchronize all processes */
```

2. **Output messages**: use `Message()` not `printf()`
```c
Message("pH = %g at cell %d\n", pH, c);   /* printed only on node 0 */
```

3. **Global reductions**: use Fluent's built-in functions
```c
real local_max = 0.0;
/* ... compute local_max ... */
real global_max = PRF_GRMAX(local_max);  /* global maximum across all nodes */
```

4. **No `exit()`**: use `Error("message")` — `exit()` kills all MPI processes.

5. **No `static` variables in cell loops**: unsafe in parallel; use UDM instead.

---

## Common UDF Mistakes

| Mistake | Consequence | Fix |
|---------|------------|-----|
| Missing `dS[eqn]` in DEFINE_SOURCE | Slow convergence, possible divergence | Always set dS, even if 0.0 |
| Using `printf` in parallel | Output appears on all nodes, may crash | Use `Message()` |
| File I/O without node-zero guard | Corrupted output files | Wrap with `if (I_AM_NODE_ZERO)` |
| Wrong species index | Wrong species modified | Verify index in *Define → Species* |
| `exit()` in error handling | Kills all MPI ranks | Use `Error("msg")` |
| Missing `#include "udf.h"` | Compilation failure | Add as first line |
