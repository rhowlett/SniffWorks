/**
 * [v0.2]
 * @file    loopback_config.h
 * @brief   Compile-time configuration for the NUCLEO-H533RE loopback DUT.
 *
 *          Every value here is a power-up DEFAULT. The PC (loopback_dut/host,
 *          reading loopback_dut/config/rig.toml) overrides addresses, speed,
 *          PEC and stretch at run time over the line protocol
 *          (loopback_dut/docs/PROTOCOL.md). Change a default here only when
 *          the rig should come up differently with no PC attached.
 */
#ifndef LOOPBACK_CONFIG_H
#define LOOPBACK_CONFIG_H

/* ---- identity ---------------------------------------------------------- */
#define LB_FW_MAJOR             0U      /* bump on releases of this firmware */
#define LB_FW_MINOR             2U      /* 0.2: address NAK reported NA */
#define LB_PROTO_VERSION        1U      /* PROTOCOL.md line-protocol version */

/* ---- I2C kernel clock (must match CubeMX: PLL3R = 64 MHz from HSE) ------ */
#ifndef LB_I2C_KERNEL_HZ
#define LB_I2C_KERNEL_HZ        64000000U   /* change only with the .ioc     */
#endif

/* ---- bus defaults ------------------------------------------------------ */
#ifndef LB_DEFAULT_SCL_HZ
#define LB_DEFAULT_SCL_HZ       100000U     /* speed until the PC sets one  */
#endif
#ifndef LB_RISE_NS
#define LB_RISE_NS              300U        /* SCL rise, 4.7k + jumpers;    */
#endif                                      /* update after measuring       */
#ifndef LB_FALL_NS
#define LB_FALL_NS              30U         /* SCL fall                     */
#endif
#ifndef LB_TAF_NS
#define LB_TAF_NS               50U         /* analog filter delay, typ     */
#endif                                      /* (DS14539); used by TIMINGR   */

/* ---- responder defaults (7-bit; PC may change them) --------------------- */
#ifndef LB_R1_ADDR
#define LB_R1_ADDR              0x6BU       /* I2C2, mirrors BQ25731        */
#endif
#ifndef LB_R2_ADDR
#define LB_R2_ADDR              0x55U       /* I2C3                         */
#endif
#define LB_R1_WORD_BASE         0xA000U     /* register map base, I2C2      */
#define LB_R2_WORD_BASE         0xB000U     /* register map base, I2C3      */
                                            /* (different so a routing bug  */
                                            /*  is visible in the value)    */

/* ---- limits ------------------------------------------------------------ */
#define LB_MAX_XFER             128U        /* bytes per master phase; LB-11 */
                                            /* reads 80 (> sniffer's 64)     */
#define LB_MAX_REPEAT           1000U       /* RUN rep= upper bound          */
#define LB_MAX_STRETCH_US       10000U      /* SET STRETCH upper bound       */
#define LB_LINE_MAX             600U        /* host command line, chars      */
#define LB_XFER_TIMEOUT_MS      50U         /* + bit time, per master phase  */

#endif /* LOOPBACK_CONFIG_H */
