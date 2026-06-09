# scene2-ip.tape — custom IP: interface port, wrapper generation

Output demo/ip.gif

Source demo/config.tape


# Type "grep -A12 '^module axi_led_ctrl' srcs/rtl/axi_led_ctrl.sv"
# Enter
# Sleep 2.5s

# Type "grep -A8 '^interface axi4_lite_if' srcs/rtl/axi_lite_if.sv"
# Enter
# Sleep 2.5s

Type "xviv create --ip axi_led_ctrl"
Enter
Sleep 15s
