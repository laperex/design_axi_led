# scene1-structure.tape — project layout, register map, project.toml overview

Output demo/structure.gif

Source demo/config.tape


Type "ls srcs/rtl/"
Enter
Sleep 1.5s

Type "grep -A6 'Register map' srcs/rtl/led_ctrl_regs.sv"
Enter
Sleep 2s

Type "grep -E '^\\[\\[|^name =|^top =|^fpga_part|^vendor|^vlnv|^backend' project.toml"
Enter
Sleep 3s
