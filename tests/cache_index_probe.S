// Static x86-64 Linux guest. Only the three loads access the data cache.
// STRIDE=64 visits three adjacent sets, STRIDE=16384 revisits one 2-way set.
.section .data
.balign 64
lines: .fill 2*STRIDE+1, 1, 1

.section .text
.globl _start
_start:
    lea lines(%rip), %rsi
    mov $4, %ecx
1:
    movb (%rsi), %al
    movb STRIDE(%rsi), %al
    movb 2*STRIDE(%rsi), %al
    dec %ecx
    jnz 1b
    mov $60, %eax
    xor %edi, %edi
    syscall
