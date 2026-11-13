/* Compile against either variant's generated address.h after building it. */
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>

#define X 0
#define Y 1
#define Z 2
typedef unsigned char BYTE;
typedef unsigned short BOOLEAN;
static short pyr_levels = 1;
static short pyr_len[1][3] = {{4, 2, 2}};
static int pyr_length[1] = {2};
static BYTE *pyr_address[1];
#include "address.h"

int main(void)
{
    pyr_address[0] = malloc(2);
    assert(pyr_address[0]);
    pyr_address[0][0] = 0x01;
    pyr_address[0][1] = 0x80;
    assert(PYR(0, 0, 0, 0) == 1);
    assert(PYR(0, 1, 1, 3) == 1);
    assert(PYR(0, 0, 0, 1) == 0);
    /* x=4 would wrap into a valid byte without per-axis checks. */
    assert(PYR(0, 0, 0, 4) == 0);
    assert(PYR(0, 0, 2, 0) == 0);
    assert(PYR(0, 2, 0, 0) == 0);
    assert(PYR(0, -1, 0, 0) == 0);
    assert(PYR(0, 0, -1, 0) == 0);
    assert(PYR(0, 0, 0, -1) == 0);
    assert(PYR(-1, 0, 0, 0) == 0);
    assert(PYR(1, 0, 0, 0) == 0);
    assert(PYR(0, LONG_MAX, LONG_MAX, LONG_MAX) == 0);
    assert(PYR(0, 0, 0, (long)UINT32_MAX) == 0);
    pyr_length[0] = 1;
    assert(PYR(0, 1, 1, 3) == 0);
    free(pyr_address[0]);
    return 0;
}
