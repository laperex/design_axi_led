"""
tests/test_project.py - basys3_led_ctrl project test suite
============================================================
Verified against xviv commit 1ef1c67 (latest).

Key API changes from b028cf3 - 1ef1c67 reflected here:
  XvivConfig(project_file=, *, work_dir=, board_repo=, ip_repo=)
  add_wrapper_cfg(ip, *, sources, ...)          [ip is now positional]
  IpConfig.fpga            (was .fpga_ref)
  CoreConfig.fpga          (was .fpga_ref)
  IpWrapperConfig.ip/.top  (was .ip_name/.ip_top)
  SynthConfig: synth_stub, synth_dcp, bitstream  (bare paths, not *_file)
  SynthConfig: out_of_context_subcores field REMOVED
  parallel_subcore_synth= is now a runtime CLI flag, not a TOML key
  Bug #1 (ip= shortform) FIXED
  Bug #2 (SynthConfig.out_files missing) FIXED - call site removed

No mocking. No Vivado required.
Run:  pytest tests/test_project.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from xviv.config.project import XvivConfig
from xviv.generator.tcl.commands import ConfigTclCommands
from xviv.utils import error

# ---------------------------------------------------------------------------
# Module-level patch check: Bug #2 is FIXED - out_files no longer called
# ---------------------------------------------------------------------------
_cmd_src = Path("/home/claude/xviv/src/xviv/generator/tcl/commands.py").read_text()
assert "out_files()" not in _cmd_src, \
    "Bug #2 regressed: out_files() call reappeared in commands.py"


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def raw_toml() -> dict:
    with open(PROJECT_ROOT / "project.toml", "rb") as f:
        return tomllib.load(f)


@pytest.fixture(scope="module")
def cfg(tmp_path_factory) -> XvivConfig:
    """Real XvivConfig built from project sources. No mocking."""
    tmp = str(tmp_path_factory.mktemp("build"))

    c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
    c.add_vivado_cfg(path="/opt/Xilinx/Vivado/2024.1/bin/vivado")
    c.add_fpga_cfg("basys3", fpga_part="xc7a35tcpg236-1")

    ip_sources = [
        str(PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi4_lite_if.sv"),
        str(PROJECT_ROOT / "srcs/ip/axi_led_ctrl/led_ctrl_regs.sv"),
        str(PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi_led_ctrl.sv"),
    ]
    c.add_ip_cfg("axi_led_ctrl", top="axi_led_ctrl", sources=ip_sources,
                 vendor="laperex", library="basys3_demo", version="1.0")

    # new: ip= is positional in add_wrapper_cfg
    c.add_wrapper_cfg("axi_led_ctrl", sources=ip_sources)

    # new: ip= shortform now works (Bug #1 fixed)
    c.add_core_cfg("clk_wiz_0",      vlnv="clk_wiz:6.0")
    c.add_core_cfg("axi_led_ctrl_0", ip="axi_led_ctrl")

    design_sources = [
        str(PROJECT_ROOT / "srcs/rtl/axi_master.sv"),
        str(PROJECT_ROOT / "srcs/rtl/top.sv"),
    ]
    c.add_design_cfg("top", top="top", sources=design_sources)

    c.add_subcore_cfg(core="clk_wiz_0",      design="top",
                      inst_hier_path="/top/u_clk_wiz_0")
    c.add_subcore_cfg(core="axi_led_ctrl_0", design="top",
                      inst_hier_path="/top/u_axi_led_ctrl_0")

    # OOC core synths
    c.add_synth_cfg(core="clk_wiz_0",      run_opt=False, run_place=False, run_route=False)
    c.add_synth_cfg(core="axi_led_ctrl_0", run_opt=False, run_place=False, run_route=False)

    # Full design synth - no out_of_context_subcores kwarg anymore
    c.add_synth_cfg(
        design="top",
        constraints=[str(PROJECT_ROOT / "constraints/basys3.xdc")],
        bitstream=True,
        route_report_timing_summary=True,
        route_report_drc=True,
    )

    sim_sources = [
        str(PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi4_lite_if.sv"),
        str(PROJECT_ROOT / "srcs/ip/axi_led_ctrl/led_ctrl_regs.sv"),
        str(PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi_led_ctrl.sv"),
        str(PROJECT_ROOT / "srcs/sim/tb_axi_led_ctrl.sv"),
    ]
    c.add_sim_cfg("tb_axi_led_ctrl", top="tb_axi_led_ctrl", sources=sim_sources,
                  backend="xsim", timescale="1ns/1ps", defines=["SIM=1"])

    # Pre-create stub XCI files (normally produced by xviv create --core)
    for name in ("clk_wiz_0", "axi_led_ctrl_0"):
        core = c.get_core(name)
        Path(core.xci_file).parent.mkdir(parents=True, exist_ok=True)
        Path(core.xci_file).touch()

    return c


def _touch_ooc_artifacts(cfg: XvivConfig) -> None:
    """Create stub.v and synth.dcp files to simulate completed OOC core synths."""
    for name in ("clk_wiz_0", "axi_led_ctrl_0"):
        s = cfg.get_synth(core_name=name)
        for path in (s.synth_stub, s.synth_dcp):
            if path:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).touch()


# ===========================================================================
# Phase 0 - TOML schema
# ===========================================================================

class TestPhase0_TomlSchema:

    def test_toml_parses(self):
        with open(PROJECT_ROOT / "project.toml", "rb") as f:
            assert isinstance(tomllib.load(f), dict)

    def test_project_section(self, raw_toml):
        assert "project" in raw_toml

    def test_fpga_part_is_basys3(self, raw_toml):
        assert raw_toml["fpga"][0]["fpga_part"] == "xc7a35tcpg236-1"

    def test_ip_section(self, raw_toml):
        assert raw_toml["ip"][0]["name"] == "axi_led_ctrl"

    def test_wrapper_references_ip(self, raw_toml):
        assert raw_toml["wrapper"][0]["ip"] == "axi_led_ctrl"

    def test_exactly_two_cores(self, raw_toml):
        assert len(raw_toml.get("core", [])) == 2

    def test_core_names(self, raw_toml):
        names = {c["name"] for c in raw_toml["core"]}
        assert "clk_wiz_0" in names and "axi_led_ctrl_0" in names

    def test_axi_led_ctrl_core_uses_ip_shortform(self, raw_toml):
        """Confirms Bug #1 fix is used in project.toml."""
        led_core = next(c for c in raw_toml["core"] if c["name"] == "axi_led_ctrl_0")
        assert "ip" in led_core, "axi_led_ctrl_0 should use ip= shortform (Bug #1 fixed)"
        assert led_core["ip"] == "axi_led_ctrl"

    def test_design_section(self, raw_toml):
        assert raw_toml["design"][0]["name"] == "top"

    def test_exactly_two_subcores(self, raw_toml):
        assert len(raw_toml.get("subcore", [])) == 2

    def test_subcores_linked_to_top(self, raw_toml):
        for sc in raw_toml["subcore"]:
            assert sc.get("design") == "top"

    def test_three_synth_entries(self, raw_toml):
        assert len(raw_toml.get("synth", [])) == 3

    def test_no_out_of_context_subcores_in_toml(self, raw_toml):
        """out_of_context_subcores= was removed from SynthConfig in 1ef1c67."""
        for s in raw_toml.get("synth", []):
            assert "out_of_context_subcores" not in s, \
                "out_of_context_subcores is no longer a TOML key (use --parallel CLI flag)"

    def test_design_synth_has_constraints(self, raw_toml):
        design_synth = next(s for s in raw_toml["synth"] if "design" in s)
        assert len(design_synth.get("constraints", [])) >= 1

    def test_simulation_section_xsim(self, raw_toml):
        assert raw_toml["simulation"][0]["backend"] == "xsim"

    def test_no_platform_section(self, raw_toml):
        assert "platform" not in raw_toml

    def test_no_app_section(self, raw_toml):
        assert "app" not in raw_toml


# ===========================================================================
# Phase 1 - Source files
# ===========================================================================

class TestPhase1_SourceFiles:

    @pytest.mark.parametrize("fname", [
        "srcs/ip/axi_led_ctrl/axi4_lite_if.sv",
        "srcs/ip/axi_led_ctrl/led_ctrl_regs.sv",
        "srcs/ip/axi_led_ctrl/axi_led_ctrl.sv",
    ])
    def test_ip_sources_exist(self, fname):
        assert (PROJECT_ROOT / fname).exists()

    @pytest.mark.parametrize("fname", ["srcs/rtl/top.sv", "srcs/rtl/axi_master.sv"])
    def test_rtl_sources_exist(self, fname):
        assert (PROJECT_ROOT / fname).exists()

    def test_sim_tb_exists(self):
        assert (PROJECT_ROOT / "srcs/sim/tb_axi_led_ctrl.sv").exists()

    def test_xdc_exists(self):
        assert (PROJECT_ROOT / "constraints/basys3.xdc").exists()

    def test_sv_interface_keyword(self):
        src = (PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi4_lite_if.sv").read_text()
        assert "interface axi4_lite_if" in src

    def test_slave_modport(self):
        src = (PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi4_lite_if.sv").read_text()
        assert "modport slave" in src

    def test_master_modport(self):
        src = (PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi4_lite_if.sv").read_text()
        assert "modport master" in src

    def test_ip_uses_interface_port(self):
        src = (PROJECT_ROOT / "srcs/ip/axi_led_ctrl/axi_led_ctrl.sv").read_text()
        assert "axi4_lite_if.slave" in src

    def test_top_instantiates_clk_wiz(self):
        src = (PROJECT_ROOT / "srcs/rtl/top.sv").read_text()
        assert "clk_wiz_0" in src

    def test_top_instantiates_wrapper(self):
        src = (PROJECT_ROOT / "srcs/rtl/top.sv").read_text()
        assert "axi_led_ctrl_wrapper" in src

    def test_top_has_sw_and_led(self):
        src = (PROJECT_ROOT / "srcs/rtl/top.sv").read_text()
        assert "sw" in src and "led" in src

    def test_xdc_clock_w5(self):
        assert "W5" in (PROJECT_ROOT / "constraints/basys3.xdc").read_text()

    def test_xdc_create_clock(self):
        assert "create_clock" in (PROJECT_ROOT / "constraints/basys3.xdc").read_text()

    def test_xdc_all_16_leds(self):
        xdc = (PROJECT_ROOT / "constraints/basys3.xdc").read_text()
        assert "led[0]" in xdc and "led[15]" in xdc

    def test_xdc_all_16_switches(self):
        xdc = (PROJECT_ROOT / "constraints/basys3.xdc").read_text()
        assert "sw[0]" in xdc and "sw[15]" in xdc

    def test_tb_has_axil_write_task(self):
        assert "axil_write" in (PROJECT_ROOT / "srcs/sim/tb_axi_led_ctrl.sv").read_text()

    def test_tb_has_pass_fail(self):
        tb = (PROJECT_ROOT / "srcs/sim/tb_axi_led_ctrl.sv").read_text()
        assert "SIMULATION PASSED" in tb and "SIMULATION FAILED" in tb


# ===========================================================================
# Phase 2 - Config API (updated field names)
# ===========================================================================

class TestPhase2_ConfigApi:

    # -- FPGA ------------------------------------------------------------------
    def test_fpga_part(self, cfg):
        assert cfg.get_fpga("basys3").fpga_part == "xc7a35tcpg236-1"

    # -- IP --------------------------------------------------------------------
    def test_ip_name_top(self, cfg):
        ip = cfg.get_ip("axi_led_ctrl")
        assert ip.name == "axi_led_ctrl" and ip.top == "axi_led_ctrl"

    def test_ip_vlnv(self, cfg):
        assert cfg.get_ip("axi_led_ctrl").vlnv == "laperex:basys3_demo:axi_led_ctrl:1.0"

    def test_ip_fpga_field(self, cfg):
        # updated: was fpga_ref, now fpga
        ip = cfg.get_ip("axi_led_ctrl")
        assert hasattr(ip, "fpga"), "IpConfig.fpga field missing (API updated)"

    def test_ip_source_count(self, cfg):
        assert len(cfg.get_ip("axi_led_ctrl").sources) == 3

    # -- Wrapper ---------------------------------------------------------------
    def test_wrapper_top_contains_wrapper(self, cfg):
        assert "wrapper" in cfg.get_wrapper("axi_led_ctrl").wrapper_top

    def test_wrapper_ip_field(self, cfg):
        # updated: was ip_name, now ip
        w = cfg.get_wrapper("axi_led_ctrl")
        assert hasattr(w, "ip"), "IpWrapperConfig.ip field missing (API updated)"
        assert w.ip == "axi_led_ctrl"

    def test_wrapper_top_field(self, cfg):
        # updated: was ip_top, now top
        w = cfg.get_wrapper("axi_led_ctrl")
        assert hasattr(w, "top"), "IpWrapperConfig.top field missing (API updated)"
        assert w.top == "axi_led_ctrl"

    def test_wrapper_file_is_sv(self, cfg):
        assert cfg.get_wrapper("axi_led_ctrl").wrapper_file.endswith(".sv")

    # -- Cores -----------------------------------------------------------------
    def test_clk_wiz_vlnv(self, cfg):
        assert "clk_wiz" in cfg.get_core("clk_wiz_0").vlnv

    def test_axi_led_ctrl_core_vlnv_inherited_from_ip(self, cfg):
        # ip= shortform now works: vlnv inherited from [[ip]]
        core = cfg.get_core("axi_led_ctrl_0")
        ip   = cfg.get_ip("axi_led_ctrl")
        assert core.vlnv == ip.vlnv

    def test_core_fpga_field(self, cfg):
        # updated: was fpga_ref, now fpga
        core = cfg.get_core("clk_wiz_0")
        assert hasattr(core, "fpga"), "CoreConfig.fpga field missing (API updated)"

    def test_xci_paths_unique(self, cfg):
        assert cfg.get_core("clk_wiz_0").xci_file != cfg.get_core("axi_led_ctrl_0").xci_file

    # -- Design ----------------------------------------------------------------
    def test_design_top(self, cfg):
        assert cfg.get_design("top").top == "top"

    def test_design_source_count(self, cfg):
        assert len(cfg.get_design("top").sources) == 2

    # -- SubCores --------------------------------------------------------------
    def test_two_subcores_in_design(self, cfg):
        assert len(cfg.get_subcore_list(design_name="top")) == 2

    def test_clk_wiz_subcore_path(self, cfg):
        sc = next(s for s in cfg.get_subcore_list(design_name="top") if s.core == "clk_wiz_0")
        assert sc.inst_hier_path == "/top/u_clk_wiz_0"

    def test_axi_led_ctrl_subcore_path(self, cfg):
        sc = next(s for s in cfg.get_subcore_list(design_name="top") if s.core == "axi_led_ctrl_0")
        assert sc.inst_hier_path == "/top/u_axi_led_ctrl_0"

    def test_subcores_no_bd_link(self, cfg):
        for sc in cfg.get_subcore_list(design_name="top"):
            assert sc.bd is None and sc.design == "top"

    # -- Synth -----------------------------------------------------------------
    def test_clk_wiz_synth_mode_ooc(self, cfg):
        assert cfg.get_synth(core_name="clk_wiz_0").synth_mode == "out_of_context"

    def test_axi_led_ctrl_synth_mode_ooc(self, cfg):
        assert cfg.get_synth(core_name="axi_led_ctrl_0").synth_mode == "out_of_context"

    def test_core_synths_have_stub_path(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            # updated: was synth_stub_file, now synth_stub
            s = cfg.get_synth(core_name=name)
            assert hasattr(s, "synth_stub"), "SynthConfig.synth_stub field missing"
            assert s.synth_stub is not None

    def test_core_synths_have_dcp_path(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            # updated: was synth_dcp_file, now synth_dcp
            s = cfg.get_synth(core_name=name)
            assert hasattr(s, "synth_dcp"), "SynthConfig.synth_dcp field missing"
            assert s.synth_dcp is not None

    def test_core_synths_no_bitstream(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            # updated: was bitstream_file, now bitstream
            assert not cfg.get_synth(core_name=name).bitstream

    def test_no_out_of_context_subcores_field(self, cfg):
        """Confirms SynthConfig no longer has out_of_context_subcores."""
        import dataclasses
        from xviv.config.model import SynthConfig
        field_names = {f.name for f in dataclasses.fields(SynthConfig)}
        assert "out_of_context_subcores" not in field_names

    def test_design_synth_has_bitstream(self, cfg):
        # updated: was bitstream_file, now bitstream
        s = cfg.get_synth(design_name="top")
        assert s.bitstream is not None

    def test_design_synth_has_one_constraint(self, cfg):
        s = cfg.get_synth(design_name="top")
        assert len(s.constraints) == 1
        assert s.constraints[0].file.endswith("basys3.xdc")

    # -- Simulation ------------------------------------------------------------
    def test_sim_top(self, cfg):
        assert cfg.get_sim("tb_axi_led_ctrl").top == "tb_axi_led_ctrl"

    def test_sim_backend_xsim(self, cfg):
        assert cfg.get_sim("tb_axi_led_ctrl").backend == "xsim"

    def test_sim_source_count(self, cfg):
        assert len(cfg.get_sim("tb_axi_led_ctrl").sources) == 4

    def test_sim_defines(self, cfg):
        assert "SIM=1" in cfg.get_sim("tb_axi_led_ctrl").defines


# ===========================================================================
# Phase 3 - Validation
# ===========================================================================

class TestPhase3_Validation:

    def test_validate_ip_passes(self, cfg):
        cfg.validate_ip("axi_led_ctrl")

    def test_validate_wrapper_passes(self, cfg):
        cfg.validate_wrapper("axi_led_ctrl")

    def test_validate_design_passes(self, cfg):
        cfg.validate_design("top")

    def test_validate_synth_passes(self, cfg):
        cfg.validate_synth(design="top")

    def test_validate_ip_fails_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_ip_cfg("bad_ip", sources=[str(Path(tmp) / "ghost.sv")])
            with pytest.raises(error.IpSourcesMissingError):
                c.validate_ip("bad_ip")

    def test_validate_design_fails_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_design_cfg("top", sources=[str(Path(tmp) / "ghost.sv")])
            with pytest.raises(error.DesignSourcesMissingError):
                c.validate_design("top")

    def test_validate_synth_fails_missing_xdc(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            src = Path(tmp) / "top.sv"; src.touch()
            c.add_design_cfg("top", sources=[str(src)])
            c.add_synth_cfg(design="top", constraints=[str(Path(tmp) / "ghost.xdc")],
                            run_opt=False, run_place=False, run_route=False, bitstream=False)
            with pytest.raises(error.SynthConstraintsMissingError):
                c.validate_synth(design="top")


# ===========================================================================
# Phase 4 - TCL generation (updated field names + new parallel_subcore_synth)
# ===========================================================================

class TestPhase4_TclGeneration:

    @pytest.fixture(scope="class")
    def tcl_clk_wiz(self, cfg) -> str:
        return ConfigTclCommands(cfg).synth(core="clk_wiz_0").build()

    @pytest.fixture(scope="class")
    def tcl_axi_led(self, cfg) -> str:
        return ConfigTclCommands(cfg).synth(core="axi_led_ctrl_0").build()

    # -- clk_wiz_0 OOC --------------------------------------------------------
    def test_clk_wiz_reads_xci(self, tcl_clk_wiz):
        assert "read_ip" in tcl_clk_wiz

    def test_clk_wiz_mode_ooc(self, tcl_clk_wiz):
        assert "-mode out_of_context" in tcl_clk_wiz

    def test_clk_wiz_writes_checkpoint(self, tcl_clk_wiz):
        assert "write_checkpoint" in tcl_clk_wiz

    def test_clk_wiz_writes_stub(self, tcl_clk_wiz):
        assert "write_verilog" in tcl_clk_wiz

    def test_clk_wiz_no_bitstream(self, tcl_clk_wiz):
        assert "write_bitstream" not in tcl_clk_wiz

    def test_clk_wiz_no_place_design(self, tcl_clk_wiz):
        assert "place_design" not in tcl_clk_wiz

    def test_clk_wiz_no_route_design(self, tcl_clk_wiz):
        assert "route_design" not in tcl_clk_wiz

    # -- axi_led_ctrl_0 OOC ---------------------------------------------------
    def test_axi_led_reads_xci(self, tcl_axi_led):
        assert "read_ip" in tcl_axi_led

    def test_axi_led_mode_ooc(self, tcl_axi_led):
        assert "-mode out_of_context" in tcl_axi_led

    def test_axi_led_writes_stub(self, tcl_axi_led):
        assert "write_verilog" in tcl_axi_led

    # -- Design synth - stubs absent - OocStubMissingError --------------------
    def test_design_synth_raises_when_stubs_missing(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            stub = cfg.get_synth(core_name=name).synth_stub
            if stub and Path(stub).exists():
                Path(stub).unlink()

        with pytest.raises(error.OocStubMissingError) as exc:
            ConfigTclCommands(cfg).synth(
                design="top", parallel_subcore_synth=True
            ).build()

        assert "clk_wiz_0" in str(exc.value) or "axi_led_ctrl_0" in str(exc.value)

    # -- Design synth - stubs present - full TCL -------------------------------
    def test_design_synth_succeeds_with_stubs(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "synth_design"    in tcl
        assert "write_bitstream" in tcl
        assert "write_checkpoint" in tcl

    def test_design_synth_adds_rtl_sources(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "top.sv"       in tcl
        assert "axi_master.sv" in tcl

    def test_design_synth_adds_stubs(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "clk_wiz_0_stub.v"      in tcl
        assert "axi_led_ctrl_0_stub.v" in tcl

    def test_design_synth_stitches_ooc_hierarchy(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "u_clk_wiz_0"      in tcl
        assert "u_axi_led_ctrl_0" in tcl

    def test_design_synth_includes_xdc(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "basys3.xdc" in tcl

    def test_design_synth_has_drc_report(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "report_drc" in tcl

    def test_design_synth_has_timing_report(self, cfg):
        _touch_ooc_artifacts(cfg)
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()
        assert "report_timing_summary" in tcl

    # -- parallel_subcore_synth=False (default) --------------------------------
    def test_design_synth_without_parallel_flag_skips_ooc_check(self, cfg):
        """Without parallel_subcore_synth=True the stub check is bypassed."""
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            stub = cfg.get_synth(core_name=name).synth_stub
            if stub and Path(stub).exists():
                Path(stub).unlink()
        # Should not raise - stubs are only checked when parallel=True
        tcl = ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=False).build()
        assert "synth_design" in tcl


# ===========================================================================
# Phase 5 - Operational sequence and bug documentation
# ===========================================================================

class TestPhase5_OperationalSequence:

    # -- Duplicates ------------------------------------------------------------
    def test_duplicate_ip_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_ip_cfg("axi_led_ctrl", sources=[])
            with pytest.raises(error.IpAlreadyExistsError):
                c.add_ip_cfg("axi_led_ctrl", sources=[])

    def test_duplicate_core_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_core_cfg("clk_wiz_0", vlnv="clk_wiz:6.0")
            with pytest.raises(error.CoreAlreadyExistsError):
                c.add_core_cfg("clk_wiz_0", vlnv="clk_wiz:6.0")

    # -- vlnv consistency -----------------------------------------------------
    def test_core_vlnv_matches_ip_vlnv(self, cfg):
        assert cfg.get_core("axi_led_ctrl_0").vlnv == cfg.get_ip("axi_led_ctrl").vlnv

    # -- XCI paths are declared ------------------------------------------------
    def test_core_xci_paths_declared(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            assert cfg.get_core(name).xci_file.endswith(".xci")

    # -- OOC stub prerequisite -------------------------------------------------
    def test_design_synth_blocked_without_stubs_when_parallel(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            stub = cfg.get_synth(core_name=name).synth_stub
            if stub and Path(stub).exists():
                Path(stub).unlink()
        with pytest.raises(error.OocStubMissingError):
            ConfigTclCommands(cfg).synth(design="top", parallel_subcore_synth=True).build()

    def test_ooc_stub_paths_contain_core_name(self, cfg):
        for name in ("clk_wiz_0", "axi_led_ctrl_0"):
            assert name in cfg.get_synth(core_name=name).synth_stub

    # -- All subcores have OOC synth --------------------------------------------
    def test_all_subcores_have_ooc_synth(self, cfg):
        for sc in cfg.get_subcore_list(design_name="top"):
            s = cfg.get_synth(core_name=sc.core)
            assert s.synth_mode == "out_of_context"

    def test_subcore_hierarchy_paths_unique(self, cfg):
        paths = [sc.inst_hier_path for sc in cfg.get_subcore_list(design_name="top")]
        assert len(paths) == len(set(paths))

    # -- Duplicate subcore raises -----------------------------------------------
    def test_duplicate_subcore_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_core_cfg("clk_wiz_0", vlnv="clk_wiz:6.0")
            src = Path(tmp) / "top.sv"; src.touch()
            c.add_design_cfg("top", sources=[str(src)])
            c.add_subcore_cfg(core="clk_wiz_0", design="top",
                              inst_hier_path="/top/u_clk_wiz_0")
            with pytest.raises(error.SubCoreDesignAlreadyExistsError):
                c.add_subcore_cfg(core="clk_wiz_0", design="top",
                                  inst_hier_path="/top/u_clk_wiz_0")

    # -- Subcore without target raises -----------------------------------------
    def test_subcore_without_target_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_core_cfg("clk_wiz_0", vlnv="clk_wiz:6.0")
            with pytest.raises(error.SubCoreIdentifierUnspecifiedError):
                c.add_subcore_cfg(core="clk_wiz_0", inst_hier_path="/top/u_clk_wiz_0")

    # -- Bug #1 FIXED ----------------------------------------------------------
    def test_bug1_ip_shortform_now_works(self):
        """Bug #1 (ip= shortform calling get_ip() without name) is FIXED in 1ef1c67."""
        with tempfile.TemporaryDirectory() as tmp:
            c = XvivConfig(project_file=str(PROJECT_ROOT / "project.toml"), work_dir=tmp)
            c.add_fpga_cfg("x", fpga_part="xc7a35tcpg236-1")
            c.add_ip_cfg("axi_led_ctrl", sources=[], vendor="laperex",
                         library="basys3_demo", version="1.0")
            # This must NOT raise TypeError anymore
            c.add_core_cfg("axi_led_ctrl_0", ip="axi_led_ctrl")
            assert c.get_core("axi_led_ctrl_0").vlnv == "laperex:basys3_demo:axi_led_ctrl:1.0"

    # -- Bug #2 FIXED ----------------------------------------------------------
    def test_bug2_out_files_call_removed(self):
        """Bug #2 (SynthConfig.out_files() called but undefined) is FIXED in 1ef1c67.
        The call site in commands.py was removed; the method was never added to the model."""
        from xviv.config.model import SynthConfig
        # Method should not exist
        assert not hasattr(SynthConfig, "out_files"), \
            "out_files() unexpectedly added - check if commands.py still calls it"
        # Call site should not exist
        assert "out_files()" not in _cmd_src, \
            "out_files() call reappeared in commands.py"

    # -- out_of_context_subcores removed ---------------------------------------
    def test_out_of_context_subcores_removed_from_synth_config(self):
        """Confirms SynthConfig.out_of_context_subcores was removed in 1ef1c67.
        OOC parallel execution is now a CLI flag: xviv synth --design top --parallel"""
        import dataclasses
        from xviv.config.model import SynthConfig
        field_names = {f.name for f in dataclasses.fields(SynthConfig)}
        assert "out_of_context_subcores" not in field_names

    # -- Full build sequence ---------------------------------------------------
    def test_full_sequence_all_steps_pass(self, cfg):
        checks = [
            ("IP declared",              lambda: cfg.get_ip("axi_led_ctrl")           is not None),
            ("Wrapper declared",         lambda: cfg.get_wrapper("axi_led_ctrl")       is not None),
            ("clk_wiz_0 declared",       lambda: cfg.get_core("clk_wiz_0")            is not None),
            ("axi_led_ctrl_0 declared",  lambda: cfg.get_core("axi_led_ctrl_0")       is not None),
            ("design top declared",      lambda: cfg.get_design("top")                is not None),
            ("2 subcores in top",        lambda: len(cfg.get_subcore_list(design_name="top")) == 2),
            ("clk_wiz OOC mode",         lambda: cfg.get_synth(core_name="clk_wiz_0").synth_mode == "out_of_context"),
            ("axi_led_ctrl_0 OOC mode",  lambda: cfg.get_synth(core_name="axi_led_ctrl_0").synth_mode == "out_of_context"),
            ("design bitstream set",     lambda: cfg.get_synth(design_name="top").bitstream is not None),
            ("simulation declared",      lambda: cfg.get_sim("tb_axi_led_ctrl")       is not None),
        ]
        failures = []
        for label, fn in checks:
            try:
                if not fn():
                    failures.append(f"FAIL: {label}")
            except Exception as exc:
                failures.append(f"ERROR: {label} - {exc}")
        assert not failures, "\n".join(failures)