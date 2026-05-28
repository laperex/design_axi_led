// =============================================================================
// axi_master.sv - Minimal AXI4-Lite Master
// Monitors sw[15:0]; writes {16'h0, sw} to address 0x00 (LED_DATA) on change.
// =============================================================================
module axi_master (
    input  logic        aclk,
    input  logic        aresetn,
    input  logic [15:0] sw,

    output logic [31:0] m_awaddr,  output logic [2:0] m_awprot,
    output logic        m_awvalid, input  logic        m_awready,
    output logic [31:0] m_wdata,   output logic [3:0]  m_wstrb,
    output logic        m_wvalid,  input  logic        m_wready,
    input  logic [1:0]  m_bresp,   input  logic        m_bvalid,
    output logic        m_bready,
    output logic [31:0] m_araddr,  output logic [2:0]  m_arprot,
    output logic        m_arvalid, input  logic        m_arready,
    input  logic [31:0] m_rdata,   input  logic [1:0]  m_rresp,
    input  logic        m_rvalid,  output logic        m_rready
);
    assign m_araddr  = 32'h0;
    assign m_arprot  = 3'h0;
    assign m_arvalid = 1'b0;
    assign m_rready  = 1'b1;

    typedef enum logic [2:0] { IDLE, WR_ADDR, WR_DATA, WR_RESP } state_t;
    state_t      state;
    logic [15:0] sw_prev;

    always_ff @(posedge aclk or negedge aresetn) begin
        if (!aresetn) begin
            state     <= IDLE; sw_prev   <= 16'hFFFF;
            m_awaddr  <= '0;   m_awprot  <= '0;  m_awvalid <= '0;
            m_wdata   <= '0;   m_wstrb   <= '0;  m_wvalid  <= '0;
            m_bready  <= '0;
        end else begin
            case (state)
                IDLE: begin
                    m_awvalid <= '0; m_wvalid <= '0; m_bready <= '0;
                    if (sw !== sw_prev) begin
                        sw_prev   <= sw;
                        m_awaddr  <= 32'h0; m_awprot <= '0; m_awvalid <= 1'b1;
                        m_wdata   <= {16'h0, sw}; m_wstrb <= 4'hF; m_wvalid <= 1'b1;
                        state     <= WR_ADDR;
                    end
                end
                WR_ADDR: begin
                    if (m_awready) begin
                        m_awvalid <= 1'b0;
                        if (m_wready) begin m_wvalid <= 1'b0; m_bready <= 1'b1; state <= WR_RESP; end
                        else state <= WR_DATA;
                    end
                end
                WR_DATA: begin
                    if (m_wready) begin m_wvalid <= 1'b0; m_bready <= 1'b1; state <= WR_RESP; end
                end
                WR_RESP: begin
                    if (m_bvalid) begin m_bready <= 1'b0; state <= IDLE; end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule