// =============================================================================
// led_ctrl_regs.sv - AXI4-Lite register file for LED / switch control
//
// Register map (byte-addressed, 32-bit registers):
//   0x00  LED_DATA   [15:0]  W/R  - drives led[15:0]
//   0x04  SW_STATUS  [15:0]  RO   - reflects sw[15:0] input
// =============================================================================
module led_ctrl_regs #(
    parameter int DATA_WIDTH = 32
) (
    input  logic                    clk,
    input  logic                    rstn,

    input  logic [31:0]             awaddr,
    input  logic                    awvalid,
    output logic                    awready,

    input  logic [DATA_WIDTH-1:0]   wdata,
    input  logic [DATA_WIDTH/8-1:0] wstrb,
    input  logic                    wvalid,
    output logic                    wready,

    output logic [1:0]              bresp,
    output logic                    bvalid,
    input  logic                    bready,

    input  logic [31:0]             araddr,
    input  logic                    arvalid,
    output logic                    arready,

    output logic [DATA_WIDTH-1:0]   rdata,
    output logic [1:0]              rresp,
    output logic                    rvalid,
    input  logic                    rready,

    input  logic [15:0]             sw,
    output logic [15:0]             led
);

    logic [15:0] reg_led_data;
    assign led = reg_led_data;

    typedef enum logic [1:0] { WR_IDLE, WR_ADDR, WR_DATA, WR_RESP } wr_state_t;
    wr_state_t wr_state;
    logic [31:0] wr_addr_latch;

    always_ff @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            wr_state      <= WR_IDLE;
            awready       <= 1'b1;
            wready        <= 1'b1;
            bvalid        <= 1'b0;
            bresp         <= 2'b00;
            reg_led_data  <= 16'h0;
            wr_addr_latch <= '0;
        end else begin
            case (wr_state)
                WR_IDLE: begin
                    bvalid <= 1'b0; awready <= 1'b1; wready <= 1'b1;
                    if (awvalid && wvalid) begin
                        wr_addr_latch <= awaddr; awready <= 1'b0; wready <= 1'b0;
                        if (awaddr[3:2] == 2'h0) begin
                            if (wstrb[0]) reg_led_data[7:0]  <= wdata[7:0];
                            if (wstrb[1]) reg_led_data[15:8] <= wdata[15:8];
                        end
                        bvalid <= 1'b1; bresp <= 2'b00; wr_state <= WR_RESP;
                    end else if (awvalid) begin
                        wr_addr_latch <= awaddr; awready <= 1'b0; wr_state <= WR_DATA;
                    end else if (wvalid) begin
                        wready <= 1'b0; wr_state <= WR_ADDR;
                    end
                end
                WR_ADDR: begin
                    if (awvalid) begin
                        wr_addr_latch <= awaddr; awready <= 1'b0;
                        if (awaddr[3:2] == 2'h0) begin
                            if (wstrb[0]) reg_led_data[7:0]  <= wdata[7:0];
                            if (wstrb[1]) reg_led_data[15:8] <= wdata[15:8];
                        end
                        bvalid <= 1'b1; bresp <= 2'b00; wr_state <= WR_RESP;
                    end
                end
                WR_DATA: begin
                    if (wvalid) begin
                        wready <= 1'b0;
                        if (wr_addr_latch[3:2] == 2'h0) begin
                            if (wstrb[0]) reg_led_data[7:0]  <= wdata[7:0];
                            if (wstrb[1]) reg_led_data[15:8] <= wdata[15:8];
                        end
                        bvalid <= 1'b1; bresp <= 2'b00; wr_state <= WR_RESP;
                    end
                end
                WR_RESP: begin
                    if (bready) begin
                        bvalid <= 1'b0; awready <= 1'b1; wready <= 1'b1;
                        wr_state <= WR_IDLE;
                    end
                end
            endcase
        end
    end

    typedef enum logic [1:0] { RD_IDLE, RD_DATA } rd_state_t;
    rd_state_t rd_state;

    always_ff @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            arready  <= 1'b1; rvalid <= 1'b0;
            rdata    <= '0;   rresp  <= 2'b00;
            rd_state <= RD_IDLE;
        end else begin
            case (rd_state)
                RD_IDLE: begin
                    rvalid <= 1'b0; arready <= 1'b1;
                    if (arvalid) begin
                        arready <= 1'b0;
                        rdata   <= (araddr[3:2] == 2'h0) ? {16'h0, reg_led_data} :
                                   (araddr[3:2] == 2'h1) ? {16'h0, sw} : '0;
                        rresp    <= 2'b00; rvalid <= 1'b1; rd_state <= RD_DATA;
                    end
                end
                RD_DATA: begin
                    if (rready) begin
                        rvalid <= 1'b0; arready <= 1'b1; rd_state <= RD_IDLE;
                    end
                end
            endcase
        end
    end
endmodule