/**
 * [v0.1]
 * @file    dut_proto.h
 * @brief   Loopback-DUT line protocol: command parser + line sealing.
 *          Pure C (no HAL); unit-tested in loopback_dut/tests/host.
 *          Normative spec: loopback_dut/docs/PROTOCOL.md.
 *
 * Host -> DUT: one ASCII command per line ('\n', '\r' ignored), tokens
 * separated by spaces, keywords case-insensitive, bytes/addresses in hex
 * (optional 0x), counts in decimal. An optional trailing " *CC" (CRC-8 of
 * every character before " *", hex) is verified when present.
 *
 * DUT -> host: every line ends " *CC\n" (always present).
 */
#ifndef DUT_PROTO_H
#define DUT_PROTO_H

#include <stdint.h>
#include <stddef.h>
#include "loopback_config.h"

typedef enum
{
    DUT_CMD_NONE = 0,       /* blank line                                   */
    DUT_CMD_PING,           /* PING                                         */
    DUT_CMD_STATUS,         /* STATUS                                       */
    DUT_CMD_RESET,          /* RESET  (counters + responder state)          */
    DUT_CMD_SET_SPEED,      /* SET SPEED <hz> [<rise_ns> <fall_ns>]         */
    DUT_CMD_SET_ADDR,       /* SET ADDR <1|2> <addr7>                       */
    DUT_CMD_SET_EN,         /* SET EN <1|2> <0|1>                           */
    DUT_CMD_SET_PEC,        /* SET PEC <1|2> <n>  (0 = off)                 */
    DUT_CMD_SET_STRETCH,    /* SET STRETCH <1|2> <byte_index> <us> (0 = off)*/
    DUT_CMD_RUN             /* RUN <seq> <op> ... [rep=<n>] [gap=<us>]      */
} dut_cmd_type_t;

typedef enum
{
    DUT_OP_W = 0,           /* W   <addr> <b..>        START W .. STOP      */
    DUT_OP_R,               /* R   <addr> <n>          START R .. STOP      */
    DUT_OP_WR,              /* WR  <addr> <n> <b..>    START W .. Sr R .. P */
    DUT_OP_WPR              /* WPR <addr> <n> <b..>    START W .. P, S R .. P*/
} dut_op_t;

typedef enum
{
    DUT_OK = 0,
    DUT_E_SYNTAX = 1,       /* unknown keyword / wrong token count          */
    DUT_E_CRC = 2,          /* trailing *CC present and wrong               */
    DUT_E_ARG = 3,          /* value out of range / not a number            */
    DUT_E_LONG = 4          /* line or payload too long                     */
} dut_err_t;

typedef struct
{
    dut_cmd_type_t type;
    /* SET */
    uint8_t  resp;          /* 1 = I2C2 (R1), 2 = I2C3 (R2)                 */
    uint32_t v1, v2, v3;    /* numeric arguments, meaning per command       */
    /* RUN */
    uint32_t seq;
    dut_op_t op;
    uint8_t  addr;
    uint16_t wlen;
    uint8_t  wdata[LB_MAX_XFER];
    uint16_t rlen;
    uint16_t rep;           /* >= 1                                         */
    uint32_t gap_us;
} dut_cmd_t;

/** Parse one line in place (the buffer is modified). */
dut_err_t dut_parse_line(char *line, dut_cmd_t *cmd);

/** CRC-8 (SMBus) over n characters. */
uint8_t dut_line_crc(const char *s, size_t n);

/** Append " *CC\n" to buf[0..len). Returns the new length, or 0 if cap is
 *  too small (buf is then unchanged). */
size_t dut_line_seal(char *buf, size_t len, size_t cap);

/** Mnemonic for an op (for echoing). */
const char *dut_op_name(dut_op_t op);

#endif /* DUT_PROTO_H */
