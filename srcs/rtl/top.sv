// =============================================================================
// top.sv - Basys3 Top-Level Design
//
// Core 1: clk_wiz_0        (Xilinx Clocking Wizard - VLNV clk_wiz:6.0)
// Core 2: axi_led_ctrl_0   (custom AXI LED controller via [[wrapper]])
//
// Both registered as [[subcore]] entries; OOC synthesised before top-level.
// Run: xviv synth --design top --parallel   (builds all OOC cores in parallel)
//
// Basys3 pin assignments in constraints/basys3.xdc.
// =============================================================================
module top (
    input  logic        clk,     // W5  - 100 MHz board oscillator
    input  logic        btnc,    // U18 - centre button -> active-high reset
    input  logic [15:0] sw,      // switches -> written to LED_DATA register
    output logic [15:0] led      // LEDs - LED_DATA register output
);

    // -- Core 1: Clock Wizard -------------------------------------------------
    logic clk_100m, clk_locked;

    clk_wiz_0 u_clk_wiz_0 (
        .clk_in1  (clk),
        .clk_out1 (clk_100m),
        .locked   (clk_locked),
        .reset    (btnc)
    );

    logic aresetn;
    assign aresetn = clk_locked & ~btnc;

    // -- AXI4-Lite internal bus ------------------------------------------------
    logic [31:0] axil_awaddr;  logic [2:0]  axil_awprot;
    logic        axil_awvalid; logic        axil_awready;
    logic [31:0] axil_wdata;   logic [3:0]  axil_wstrb;
    logic        axil_wvalid;  logic        axil_wready;
    logic [1:0]  axil_bresp;   logic        axil_bvalid;  logic axil_bready;
    logic [31:0] axil_araddr;  logic [2:0]  axil_arprot;
    logic        axil_arvalid; logic        axil_arready;
    logic [31:0] axil_rdata;   logic [1:0]  axil_rresp;
    logic        axil_rvalid;  logic        axil_rready;

    // -- AXI Master: sw changes -> AXI write ------------------------------------
    axi_master u_axi_master (
        .aclk     (clk_100m), .aresetn   (aresetn), .sw        (sw),
        .m_awaddr (axil_awaddr), .m_awprot (axil_awprot), .m_awvalid (axil_awvalid),
        .m_awready(axil_awready),
        .m_wdata  (axil_wdata),  .m_wstrb  (axil_wstrb),  .m_wvalid  (axil_wvalid),
        .m_wready (axil_wready),
        .m_bresp  (axil_bresp),  .m_bvalid (axil_bvalid), .m_bready  (axil_bready),
        .m_araddr (axil_araddr), .m_arprot (axil_arprot), .m_arvalid (axil_arvalid),
        .m_arready(axil_arready),.m_rdata  (axil_rdata),  .m_rresp   (axil_rresp),
        .m_rvalid (axil_rvalid), .m_rready  (axil_rready)
    );

    // -- Core 2: AXI LED Controller (via [[wrapper]]-generated wrapper) --------
    axi_led_ctrl_wrapper u_axi_led_ctrl_0 (
        .aclk           (clk_100m), .aresetn        (aresetn),
        .s_axil_awaddr  (axil_awaddr),  .s_axil_awprot  (axil_awprot),
        .s_axil_awvalid (axil_awvalid), .s_axil_awready (axil_awready),
        .s_axil_wdata   (axil_wdata),   .s_axil_wstrb   (axil_wstrb),
        .s_axil_wvalid  (axil_wvalid),  .s_axil_wready  (axil_wready),
        .s_axil_bresp   (axil_bresp),   .s_axil_bvalid  (axil_bvalid),
        .s_axil_bready  (axil_bready),
        .s_axil_araddr  (axil_araddr),  .s_axil_arprot  (axil_arprot),
        .s_axil_arvalid (axil_arvalid), .s_axil_arready (axil_arready),
        .s_axil_rdata   (axil_rdata),   .s_axil_rresp   (axil_rresp),
        .s_axil_rvalid  (axil_rvalid),  .s_axil_rready  (axil_rready),
        .sw(sw), .led(led)
    );

endmodule