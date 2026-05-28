// =============================================================================
// axi_led_ctrl.sv - AXI4-Lite LED Controller IP Top Module
//
// Top port uses axi4_lite_if.slave - triggers [[wrapper]] generation.
// Register map: 0x00 LED_DATA [15:0] W/R | 0x04 SW_STATUS [15:0] RO
// =============================================================================
module axi_led_ctrl #(
    parameter int DATA_WIDTH = 32
) (
    input  logic              aclk,
    input  logic              aresetn,
    axi4_lite_if.slave        s_axil,
    input  logic [15:0]       sw,
    output logic [15:0]       led
);
    led_ctrl_regs #(.DATA_WIDTH(DATA_WIDTH)) u_regs (
        .clk     (aclk),    .rstn    (aresetn),
        .awaddr  (s_axil.awaddr),  .awvalid (s_axil.awvalid), .awready (s_axil.awready),
        .wdata   (s_axil.wdata),   .wstrb   (s_axil.wstrb),   .wvalid  (s_axil.wvalid),
        .wready  (s_axil.wready),
        .bresp   (s_axil.bresp),   .bvalid  (s_axil.bvalid),  .bready  (s_axil.bready),
        .araddr  (s_axil.araddr),  .arvalid (s_axil.arvalid), .arready (s_axil.arready),
        .rdata   (s_axil.rdata),   .rresp   (s_axil.rresp),   .rvalid  (s_axil.rvalid),
        .rready  (s_axil.rready),
        .sw(sw), .led(led)
    );
endmodule