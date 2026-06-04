// =============================================================================
// tb_axi_led_ctrl.sv  –  Testbench for axi_led_ctrl IP
//
// Target simulator : Vivado XSim  (set in project.toml: backend = "xsim")
// Timescale        : 1ns / 1ps    (set in project.toml)
//
// DUT register map
//   0x00  LED_DATA   [15:0]  R/W  – drives   led[15:0]
//   0x04  SW_STATUS  [15:0]  RO   – reflects sw[15:0]
//
// Test cases
//   TC01  Post-reset LED value = 0
//   TC02  Write LED_DATA 0xDEAD   (combined AW+W)
//   TC03  Readback LED_DATA
//   TC04  SW_STATUS passthrough
//   TC05  Write to RO SW_STATUS   (write ignored)
//   TC06  Byte-strobe low  byte only  (wstrb = 4'h1)
//   TC07  Byte-strobe high byte only  (wstrb = 4'h2)
//   TC08  AW-first split write
//   TC09  W-first  split write
//   TC10  Three back-to-back sequential writes
//   TC11  Write then immediate read
//   TC12  Live SW update reflected in SW_STATUS
//   TC13  Mid-sim reset clears LED_DATA
// =============================================================================
`timescale 1ns/1ps

module tb_axi_led_ctrl;

    // =========================================================================
    // Parameters / addresses
    // =========================================================================
    localparam int  DATA_WIDTH = 32;
    localparam real CLK_HALF   = 5.0;   // 100 MHz  (10 ns period)

    localparam logic [31:0] ADDR_LED_DATA  = 32'h0000_0000;
    localparam logic [31:0] ADDR_SW_STATUS = 32'h0000_0004;

    // =========================================================================
    // Clock & reset
    // =========================================================================
    logic aclk    = 1'b0;
    logic aresetn = 1'b0;

    always #CLK_HALF aclk = ~aclk;

    // =========================================================================
    // Interface and DUT instantiation
    // =========================================================================
    axi4_lite_if #(.ADDR_WIDTH(32), .DATA_WIDTH(DATA_WIDTH)) axil ();

    logic [15:0] sw  = 16'h0000;
    logic [15:0] led;

    axi_led_ctrl #(.DATA_WIDTH(DATA_WIDTH)) dut (
        .aclk    (aclk),
        .aresetn (aresetn),
        .s_axil  (axil),        // interface port; slave modport applied inside DUT
        .sw      (sw),
        .led     (led)
    );

    // =========================================================================
    // Scoreboard helpers
    // =========================================================================
    int pass_cnt = 0;
    int fail_cnt = 0;

    task automatic check_eq (
        input string      name,
        input logic [31:0] got,
        input logic [31:0] exp
    );
        if (got === exp) begin
            $display("[PASS] %7.1f ns | %-46s | got=0x%08x",
                     $realtime, name, got);
            pass_cnt++;
        end else begin
            $display("[FAIL] %7.1f ns | %-46s | got=0x%08x  exp=0x%08x",
                     $realtime, name, got, exp);
            fail_cnt++;
        end
    endtask

    // =========================================================================
    // Watchdog  –  kills runaway sims
    // =========================================================================
    initial begin
        #50_000;
        $display("[WATCHDOG] Simulation exceeded 50 µs – aborting");
        $finish;
    end

    // =========================================================================
    // AXI4-Lite master tasks
    //
    // Timing convention:
    //   • Signals are driven after @(negedge aclk) to give setup margin.
    //   • Handshakes are detected with  do @(posedge aclk); while(!cond)
    //     which polls in the active region (registered DUT outputs from the
    //     previous cycle's NBA are stable there).
    // =========================================================================

    // -------------------------------------------------------------------------
    // axil_write  –  standard combined AW+W path
    //   The DUT accepts AW and W simultaneously in WR_IDLE (awready=1,
    //   wready=1), so both handshakes fire on the same posedge.
    // -------------------------------------------------------------------------
    task automatic axil_write (
        input logic [31:0] addr,
        input logic [31:0] data,
        input logic [3:0]  strb = 4'hF
    );
        @(negedge aclk);
        axil.awaddr  = addr;   axil.awprot  = 3'b000;  axil.awvalid = 1'b1;
        axil.wdata   = data;   axil.wstrb   = strb;     axil.wvalid  = 1'b1;

        // AW + W handshakes (simultaneous in IDLE): wait for awready high
        do @(posedge aclk); while (!(axil.awvalid && axil.awready));
        @(negedge aclk);
        axil.awvalid = 1'b0;
        axil.wvalid  = 1'b0;

        // B-channel: bvalid appears one cycle after the handshake
        axil.bready  = 1'b1;
        do @(posedge aclk); while (!axil.bvalid);
        @(negedge aclk);
        axil.bready  = 1'b0;
    endtask

    // -------------------------------------------------------------------------
    // axil_write_aw_first  –  AW channel arrives before W channel
    //   DUT transitions: WR_IDLE → WR_DATA (wready still 1) → WR_RESP
    // -------------------------------------------------------------------------
    task automatic axil_write_aw_first (
        input logic [31:0] addr,
        input logic [31:0] data,
        input logic [3:0]  strb = 4'hF
    );
        // Phase 1: AW only
        @(negedge aclk);
        axil.awaddr  = addr;  axil.awprot  = 3'b000;  axil.awvalid = 1'b1;

        do @(posedge aclk); while (!(axil.awvalid && axil.awready));
        @(negedge aclk);
        axil.awvalid = 1'b0;

        // Phase 2: W channel  (DUT is in WR_DATA, wready = 1)
        axil.wdata   = data;  axil.wstrb   = strb;  axil.wvalid  = 1'b1;

        do @(posedge aclk); while (!(axil.wvalid && axil.wready));
        @(negedge aclk);
        axil.wvalid  = 1'b0;

        // B-channel
        axil.bready  = 1'b1;
        do @(posedge aclk); while (!axil.bvalid);
        @(negedge aclk);
        axil.bready  = 1'b0;
    endtask

    // -------------------------------------------------------------------------
    // axil_write_w_first  –  W channel arrives before AW channel
    //   DUT transitions: WR_IDLE → WR_ADDR (awready still 1) → WR_RESP
    //   NOTE: wdata/wstrb must remain stable through the AW phase because
    //   the DUT reads them from the bus when awvalid arrives in WR_ADDR.
    // -------------------------------------------------------------------------
    task automatic axil_write_w_first (
        input logic [31:0] addr,
        input logic [31:0] data,
        input logic [3:0]  strb = 4'hF
    );
        // Phase 1: W only – do NOT clear wdata/wstrb between phases
        @(negedge aclk);
        axil.wdata   = data;  axil.wstrb   = strb;  axil.wvalid  = 1'b1;
        axil.awvalid = 1'b0;

        do @(posedge aclk); while (!(axil.wvalid && axil.wready));
        @(negedge aclk);
        axil.wvalid  = 1'b0;
        // wdata/wstrb intentionally kept at their values

        // Phase 2: AW channel  (DUT is in WR_ADDR, awready = 1)
        axil.awaddr  = addr;  axil.awprot  = 3'b000;  axil.awvalid = 1'b1;

        do @(posedge aclk); while (!(axil.awvalid && axil.awready));
        @(negedge aclk);
        axil.awvalid = 1'b0;

        // B-channel
        axil.bready  = 1'b1;
        do @(posedge aclk); while (!axil.bvalid);
        @(negedge aclk);
        axil.bready  = 1'b0;
    endtask

    // -------------------------------------------------------------------------
    // axil_read  –  standard AR→R read
    //   rready is asserted before arvalid (AXI permits this).  rdata is
    //   captured at the posedge where rvalid first appears (active region;
    //   the value was written by the previous posedge's NBA and is stable).
    // -------------------------------------------------------------------------
    task automatic axil_read (
        input  logic [31:0]  addr,
        output logic [31:0]  rdata_out
    );
        @(negedge aclk);
        axil.araddr  = addr;  axil.arprot  = 3'b000;  axil.arvalid = 1'b1;
        axil.rready  = 1'b1;  // assert early — legal per AXI4-Lite spec

        do @(posedge aclk); while (!(axil.arvalid && axil.arready));
        @(negedge aclk);
        axil.arvalid = 1'b0;

        // rdata / rvalid appear one cycle after the AR handshake
        do @(posedge aclk); while (!axil.rvalid);
        rdata_out    = axil.rdata;   // stable: set by previous posedge's NBA
        @(negedge aclk);
        axil.rready  = 1'b0;
    endtask

    // =========================================================================
    // Main test sequence
    // =========================================================================
    logic [31:0] rdata;

    initial begin
        $timeformat(-9, 1, " ns", 10);

        // -- Initialise all master-driven signals to 0 -----------------------
        axil.awaddr  = '0;  axil.awprot  = '0;  axil.awvalid = 1'b0;
        axil.wdata   = '0;  axil.wstrb   = '0;  axil.wvalid  = 1'b0;
        axil.bready  = 1'b0;
        axil.araddr  = '0;  axil.arprot  = '0;  axil.arvalid = 1'b0;
        axil.rready  = 1'b0;

        // -- Reset sequence --------------------------------------------------
        aresetn = 1'b0;
        repeat (5) @(posedge aclk);
        @(negedge aclk);
        aresetn = 1'b1;
        repeat (2) @(posedge aclk);

        $display("\n=== Reset de-asserted @ %7.1f ns ===\n", $realtime);

        // ------------------------------------------------------------------ //
        // TC01 – Post-reset: led should be all-zero                          //
        // ------------------------------------------------------------------ //
        $display("--- TC01: Post-reset LED value ---");
        check_eq("led[15:0] after reset", {16'h0, led}, 32'h0000_0000);

        // ------------------------------------------------------------------ //
        // TC02 – Write LED_DATA = 0xDEAD  (combined AW+W)                   //
        // ------------------------------------------------------------------ //
        $display("--- TC02: Write LED_DATA = 0xDEAD (combined AW+W) ---");
        axil_write(ADDR_LED_DATA, 32'h0000_DEAD);
        @(posedge aclk);
        check_eq("led = 0xDEAD", {16'h0, led}, 32'h0000_DEAD);

        // ------------------------------------------------------------------ //
        // TC03 – Read back LED_DATA register                                 //
        // ------------------------------------------------------------------ //
        $display("--- TC03: Readback LED_DATA ---");
        axil_read(ADDR_LED_DATA, rdata);
        check_eq("rdata[LED_DATA] == 0xDEAD", rdata, 32'h0000_DEAD);

        // ------------------------------------------------------------------ //
        // TC04 – SW_STATUS passthrough  (sw = 0xA5C3)                       //
        // ------------------------------------------------------------------ //
        $display("--- TC04: SW_STATUS passthrough ---");
        sw = 16'hA5C3;
        repeat (2) @(posedge aclk);
        axil_read(ADDR_SW_STATUS, rdata);
        check_eq("rdata[SW_STATUS] == 0xA5C3", rdata, 32'h0000_A5C3);

        // ------------------------------------------------------------------ //
        // TC05 – Write to RO register SW_STATUS (0x04) – must be ignored     //
        // ------------------------------------------------------------------ //
        $display("--- TC05: Write to RO SW_STATUS (ignored) ---");
        axil_write(ADDR_SW_STATUS, 32'hFFFF_FFFF);
        @(posedge aclk);
        check_eq("led unchanged after RO write", {16'h0, led}, 32'h0000_DEAD);

        // ------------------------------------------------------------------ //
        // TC06 – Byte-strobe: low byte only  (wstrb = 4'h1)                 //
        //   Before : led = 0xDEAD                                            //
        //   Write  : wdata[7:0] = 0xBE, wstrb = 4'h1                        //
        //   After  : led = 0xDE_BE  (high byte unchanged)                   //
        // ------------------------------------------------------------------ //
        $display("--- TC06: Byte-strobe low byte 0xBE (wstrb=4'h1) ---");
        axil_write(ADDR_LED_DATA, 32'h0000_00BE, 4'h1);
        @(posedge aclk);
        check_eq("led low=0xBE, high=0xDE", {16'h0, led}, 32'h0000_DEBE);

        // ------------------------------------------------------------------ //
        // TC07 – Byte-strobe: high byte only  (wstrb = 4'h2)                //
        //   Before : led = 0xDEBE                                            //
        //   Write  : wdata[15:8] = 0xAB, wstrb = 4'h2                       //
        //   After  : led = 0xAB_BE  (low byte unchanged)                    //
        // ------------------------------------------------------------------ //
        $display("--- TC07: Byte-strobe high byte 0xAB (wstrb=4'h2) ---");
        axil_write(ADDR_LED_DATA, 32'h0000_AB00, 4'h2);
        @(posedge aclk);
        check_eq("led low=0xBE, high=0xAB", {16'h0, led}, 32'h0000_ABBE);

        // ------------------------------------------------------------------ //
        // TC08 – AW-first split write  →  0x1234                            //
        // ------------------------------------------------------------------ //
        $display("--- TC08: AW-first split write -> 0x1234 ---");
        axil_write_aw_first(ADDR_LED_DATA, 32'h0000_1234);
        @(posedge aclk);
        check_eq("led after AW-first write", {16'h0, led}, 32'h0000_1234);

        // ------------------------------------------------------------------ //
        // TC09 – W-first split write  →  0x5678                             //
        // ------------------------------------------------------------------ //
        $display("--- TC09: W-first split write -> 0x5678 ---");
        axil_write_w_first(ADDR_LED_DATA, 32'h0000_5678);
        @(posedge aclk);
        check_eq("led after W-first write", {16'h0, led}, 32'h0000_5678);

        // ------------------------------------------------------------------ //
        // TC10 – Three back-to-back sequential writes                        //
        // ------------------------------------------------------------------ //
        $display("--- TC10: 3 sequential writes ---");
        axil_write(ADDR_LED_DATA, 32'h0000_CAFE);
        axil_write(ADDR_LED_DATA, 32'h0000_BABE);
        axil_write(ADDR_LED_DATA, 32'h0000_F00D);
        @(posedge aclk);
        check_eq("led after 3 sequential writes", {16'h0, led}, 32'h0000_F00D);

        // ------------------------------------------------------------------ //
        // TC11 – Write then immediate read (no idle gap)                     //
        // ------------------------------------------------------------------ //
        $display("--- TC11: Write 0xBEEF then immediate read ---");
        axil_write(ADDR_LED_DATA, 32'h0000_BEEF);
        axil_read(ADDR_LED_DATA, rdata);
        check_eq("rdata LED_DATA == 0xBEEF", rdata, 32'h0000_BEEF);

        // ------------------------------------------------------------------ //
        // TC12 – Live SW update reflected in SW_STATUS                       //
        // ------------------------------------------------------------------ //
        $display("--- TC12: SW live update -> SW_STATUS (sw=0x0F0F) ---");
        sw = 16'h0F0F;
        @(posedge aclk); // sw is combinatorial into rdata mux
        axil_read(ADDR_SW_STATUS, rdata);
        check_eq("SW_STATUS == 0x0F0F", rdata, 32'h0000_0F0F);

        // ------------------------------------------------------------------ //
        // TC13 – Mid-sim reset clears LED_DATA                               //
        // ------------------------------------------------------------------ //
        $display("--- TC13: Mid-sim reset clears LED ---");
        @(negedge aclk);
        aresetn = 1'b0;
        repeat (3) @(posedge aclk);
        check_eq("led cleared by mid-sim reset", {16'h0, led}, 32'h0000_0000);

        // Re-init master-driven signals and release reset
        @(negedge aclk);
        axil.awvalid = 1'b0;  axil.wvalid  = 1'b0;
        axil.bready  = 1'b0;  axil.arvalid = 1'b0;  axil.rready = 1'b0;
        aresetn = 1'b1;
        repeat (2) @(posedge aclk);

        // ------------------------------------------------------------------ //
        // Summary                                                             //
        // ------------------------------------------------------------------ //
        repeat (5) @(posedge aclk);
        $display("\n============================================");
        $display("  SIMULATION COMPLETE  @ %7.1f ns", $realtime);
        $display("  PASS : %0d", pass_cnt);
        $display("  FAIL : %0d", fail_cnt);
        $display("============================================");
        if (fail_cnt == 0)
            $display("  >>> ALL %0d TESTS PASSED <<<\n", pass_cnt);
        else
            $display("  >>> %0d TEST(S) FAILED  <<<\n", fail_cnt);

        $finish;
    end

endmodule