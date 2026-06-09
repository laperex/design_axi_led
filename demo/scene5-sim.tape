# scene4-synth-sim.tape — synthesis pipeline + simulation dry-runs

Output demo/sim.gif

Source demo/config.tape


# Type "xviv synth --core axi_led_ctrl_0 --dry-run 2>&1 | head -35"
# Enter
# Sleep 4s

# Type "xviv synth --design top --parallel"
# Enter
# Sleep 140s

Type "xviv simulate --target tb_axi_led_ctrl"
Enter
Sleep 7s

# Type "grep '//   TC' srcs/sim/tb_axi_led_ctrl.sv"
# Enter
# Sleep 3s
