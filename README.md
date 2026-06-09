# design_axi_led

AXI4-Lite LED controller demo for the **Basys3** (`xc7a35tcpg236-1`).

A custom AXI4-Lite peripheral is packaged as a Vivado IP, OOC-synthesised, then instantiated in
a top-level design alongside a Xilinx Clocking Wizard. An on-chip AXI master watches the 16
slide-switches and writes their value to the LED register on every change — the LEDs mirror the
switches entirely through AXI register writes over an internal bus.

Built and managed with [xviv](https://github.com/laperex/xviv).

---

## Project structure

```
design_axi_led/
├── project.toml              # xviv project config
├── constraints/
│   └── basys3.xdc
└── srcs/
    ├── rtl/
    │   ├── axi_lite_if.sv    # AXI4-Lite SV interface (master/slave modports)
    │   ├── led_ctrl_regs.sv  # register file — AXI4-Lite slave FSM
    │   ├── axi_led_ctrl.sv   # IP top (uses axi4_lite_if.slave port)
    │   ├── axi_master.sv     # on-chip master — writes sw on change
    │   └── top.sv            # Basys3 top: clk_wiz_0 + axi_led_ctrl_0
    └── sim/
        └── tb_axi_led_ctrl.sv  # IP-level testbench, 13 test cases
```

### Signal flow

```
clk (100 MHz) ──► clk_wiz_0 ──► clk_100m ──┬──► axi_master ──AXI4-Lite──► axi_led_ctrl_0 ──► led[15:0]
btnc ────────────────────────────────────────┘   (writes sw on change)      (register slave)
sw[15:0] ────────────────────────────────────────────────────────────────►  SW_STATUS (RO)
```

### Register map

| Offset | Name | Access | Bits | Description |
|--------|------|--------|------|-------------|
| `0x00` | `LED_DATA` | R/W | `[15:0]` | Drives `led[15:0]` |
| `0x04` | `SW_STATUS` | RO | `[15:0]` | Reflects `sw[15:0]`; writes ignored |

---

## Custom IP and wrapper generation

<img src="demo/ip.gif" width="800" alt="IP packaging and wrapper generation" />

`axi_led_ctrl` uses a SystemVerilog interface port (`axi4_lite_if.slave s_axil`). Vivado's IP
Packager cannot infer AXI bus interfaces from interface ports, so `[[wrapper]]` in `project.toml`
instructs xviv to generate a flattened wrapper (`axi_led_ctrl_wrapper.sv`) via `pyslang` —
exposing all AXI signals as scalar ports (`s_axil_awaddr`, `s_axil_wdata`, …). The wrapper is
what gets packaged and instantiated as `axi_led_ctrl_0` in `top.sv`.

---

## Constraint validation

<img src="demo/validate.gif" width="800" alt="XDC constraint validation" />

`xviv validate` cross-references XDC pin assignments against RTL port declarations using Python's
built-in Tcl engine and `pyslang` — no Vivado license needed. Useful as a fast CI gate before
committing to a full synthesis run.

```sh
# Summary — total / constrained / unconstrained counts
xviv validate synth --design top --io short

# Full per-port table: PIN, IOSTANDARD, timing flags, status
xviv validate synth --design top --io full

# CI-friendly — exits non-zero if any port is unconstrained or unmatched
xviv validate synth --design top --io full --level error
```

---

## Synthesis

<img src="demo/synth.gif" width="800" alt="synthesis run" />

## Simulation

<img src="demo/sim.gif" width="800" alt="synthesis run" />

### Build

```sh
# Package custom IP (generates AXI wrapper via pyslang)
xviv create --ip axi_led_ctrl

# Instantiate catalog cores
xviv create --core clk_wiz_0
xviv create --core axi_led_ctrl_0

# Full build — OOC synth of both cores in parallel, then top impl
xviv synth --design top --parallel
```

Outputs in `build/synth/top/`:

```
top.bit
checkpoints/{synth,place,route}.dcp
reports/route_report_timing_summary_file.rpt
reports/route_report_drc_file.rpt
```

### Program

```sh
xviv program --bitstream build/synth/top/top.bit
```

### Simulate

IP-level testbench (`xsim`, 13 test cases):

| TC | Description |
|----|-------------|
| TC01 | Post-reset `led` = 0 |
| TC02 | Combined AW+W write to `LED_DATA` |
| TC03 | Readback `LED_DATA` |
| TC04 | `SW_STATUS` passthrough |
| TC05 | Write to RO `SW_STATUS` — ignored |
| TC06 | Byte-strobe low byte (`wstrb = 4'h1`) |
| TC07 | Byte-strobe high byte (`wstrb = 4'h2`) |
| TC08 | AW-first split write |
| TC09 | W-first split write |
| TC10 | Three back-to-back sequential writes |
| TC11 | Write then immediate read |
| TC12 | Live `sw` update in `SW_STATUS` |
| TC13 | Mid-sim reset clears `LED_DATA` |

```sh
xviv simulate --target tb_axi_led_ctrl
xviv open --wdb tb_axi_led_ctrl
```

### Incremental builds

```sh
# Resume from latest available checkpoint
xviv synth --design top --resume auto

# Only XDC changed — re-run write_bitstream only
xviv synth --design top --resume route

# RTL changed — re-run from opt onward
xviv synth --design top --resume synth
```

---

## Prerequisites

- Python ≥ 3.11
- Vivado 2024.1 or 2024.2

```sh
pip install xviv
```

Set the Vivado path in `.env` at the project root (add to `.gitignore`):

```sh
XVIV_VIVADO_SOURCE_SCRIPT=/tools/Xilinx/Vivado/2024.1/settings64.sh
```

---

## Regenerate demo GIFs

Requires [VHS](https://github.com/charmbracelet/vhs).

```sh
make        # renders all four demo/**.gif
make clean  # removes generated GIFs
```