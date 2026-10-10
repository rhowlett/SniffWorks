/**
 * [v0.2]
 ******************************************************************************
 * @file    frame_protocol.h
 * @brief   Binary UART framing between the Nucleo sniffer firmware and the
 *          host application (sniffer_nucleoC0.py).
 *
 *          Full specification: embedded/docs/PROTOCOL.md
 *          Keep this header, the Python parser, and PROTOCOL.md in sync.
 *
 * Device -> Host frame:
 *   [0xAA][type][len_lo][len_hi][payload ...][crc8]
 *   crc8 = SMBus CRC-8 (poly 0x07, init 0x00) over type..payload inclusive.
 *
 * Host -> Device command:
 *   [0xA5][cmd][arg][crc8]
 *   crc8 over cmd..arg.
 ******************************************************************************
 */
#ifndef FRAME_PROTOCOL_H
#define FRAME_PROTOCOL_H

#include <stdint.h>
#include "i2c_bitbang_decoder.h"   /* i2c_txn_t */

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------------ */
/* Framing constants                                                         */
/* ------------------------------------------------------------------------ */
#define FRAME_SYNC_DEV2HOST     0xAAU
#define FRAME_SYNC_HOST2DEV     0xA5U

/* Device -> Host frame types */
#define FRAME_TYPE_TXN          0x01U
#define FRAME_TYPE_STATUS       0x02U
#define FRAME_TYPE_ERROR        0x03U
#define FRAME_TYPE_HELLO        0x04U

/* Host -> Device commands */
#define CMD_START               0x01U
#define CMD_STOP                0x02U
#define CMD_STATUS_REQ          0x03U
#define CMD_PING                0x04U
#define CMD_RESET_COUNTS        0x05U

/* Master-mode commands (variable-length form, SNIFF_MODE_MASTER firmware):
 *   [0xA5][cmd][len][payload ...][crc8]   crc8 over cmd..payload           */
#define CMD_I2C_WRITE           0x10U   /* payload: addr7, data[]           */
#define CMD_I2C_WRITE_READ      0x11U   /* payload: addr7, wlen, wdata, rlen*/
#define CMD_I2C_READ            0x12U   /* payload: addr7, rlen             */
#define CMD_SET_BUS_SPEED       0x13U   /* payload: 0=100 kHz, 1=400 kHz    */
#define CMD_VAR_MIN             0x10U   /* first variable-length command    */
#define CMD_MAX_PAYLOAD         72U     /* addr+wlen+64 data+rlen+margin    */

/* TXN flags byte */
#define TXN_FLAG_DIR_READ       (1U << 0)
#define TXN_FLAG_NAK            (1U << 1)
#define TXN_FLAG_RESTART        (1U << 2)
#define TXN_FLAG_STOP           (1U << 3)
#define TXN_FLAG_OVERFLOW       (1U << 4)
#define TXN_FLAG_TIMEOUT        (1U << 5)   /* master: transfer timed out   */
#define TXN_FLAG_FRAMING        (1U << 6)   /* bit-slipped phase (lost edge) */

/* ERROR codes */
#define ERR_CODE_RING_OVERFLOW  0x01U   /* TXN frame dropped, ring full     */
#define ERR_CODE_BAD_COMMAND    0x02U   /* malformed / unknown host command */
#define ERR_CODE_BUS_ERROR      0x03U   /* decoder framing anomaly          */

/* Capture state reported in STATUS */
#define CAPTURE_STATE_IDLE      0x00U
#define CAPTURE_STATE_RUNNING   0x01U

/* HELLO magic ("NC0S" little-endian on the wire) */
#define HELLO_MAGIC_0           'N'
#define HELLO_MAGIC_1           'C'
#define HELLO_MAGIC_2           '0'
#define HELLO_MAGIC_3           'S'

/* Worst-case encoded frame size (TXN with full payload + u32 scl_hz)       */
#define FRAME_MAX_ENCODED       (4U + 7U + TXN_MAX_DATA + 4U + 1U)

/* ------------------------------------------------------------------------ */
/* SMBus CRC-8 (poly 0x07, init 0x00) - same algorithm as the Python side   */
/* ------------------------------------------------------------------------ */
uint8_t frame_crc8(const uint8_t *data, uint32_t len);
uint8_t frame_crc8_cont(uint8_t crc, const uint8_t *data, uint32_t len);
extern const uint8_t frame_crc8_table[256];   /* fw 1.4 lookup table      */

/* ------------------------------------------------------------------------ */
/* Encoders: write a complete frame into buf, return encoded length.        */
/* buf must be at least FRAME_MAX_ENCODED bytes.                            */
/* ------------------------------------------------------------------------ */
uint32_t frame_encode_txn(uint8_t *buf, const i2c_txn_t *txn);

typedef struct
{
    uint8_t  proto_ver;
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  mode;          /* SNIFF_MODE_* value                           */
    uint8_t  state;         /* CAPTURE_STATE_*                              */
    uint32_t captured;      /* transactions captured since start/reset      */
    uint32_t errors;        /* decoder/bus errors                           */
    uint32_t dropped;       /* TXN frames dropped due to ring overflow      */
    uint32_t bus_hz;        /* estimated bus clock, 0 = unknown             */
    /* fw 1.4 sampler diagnostics (encoded only when diag_valid != 0).      */
    /* Ticks are SYSCLK cycles (48 MHz); 0xFFFF = none seen / saturated.   */
    uint8_t  diag_valid;
    uint16_t diag_max_gap;      /* longest sample gap, transaction open    */
    uint16_t diag_min_high;     /* narrowest SCL high pulse                */
    uint16_t diag_min_low;      /* narrowest SCL low pulse                 */
    uint32_t diag_gaps_2us;     /* sample gaps > 2 us, transaction open    */
    uint32_t diag_framing;      /* phases flagged FRAMING                  */
    uint16_t diag_frm_max_gap;  /* worst gap inside a FRAMING phase        */
    uint16_t diag_frm_min_high; /* narrowest SCL high in a FRAMING phase   */
    uint32_t diag_deferred;     /* upkeep slots deferred (B30 mitigation)  */
} status_info_t;

#define STATUS_PAYLOAD_LEN       21U
#define STATUS_DIAG_PAYLOAD_LEN  45U
#define STATUS_DIAG_VERSION      1U

uint32_t frame_encode_status(uint8_t *buf, const status_info_t *st);
uint32_t frame_encode_error(uint8_t *buf, uint8_t code, uint8_t detail);
uint32_t frame_encode_hello(uint8_t *buf, uint8_t mode);

/* ------------------------------------------------------------------------ */
/* Host->Device command parser (byte-at-a-time, resync on bad CRC)          */
/* ------------------------------------------------------------------------ */
typedef struct
{
    uint8_t state;          /* 0 sync, 1 cmd, 2 arg|len, 3 crc, 4 payload   */
    uint8_t len;            /* var-length: expected payload bytes           */
    uint8_t idx;            /* var-length: payload bytes received           */
    uint8_t payload[CMD_MAX_PAYLOAD];
    uint8_t cmd;
    uint8_t arg;
} cmd_parser_t;

typedef enum
{
    CMD_EVT_NONE = 0,
    CMD_EVT_COMMAND,        /* parser->cmd / parser->arg are valid          */
    CMD_EVT_BAD_CRC
} cmd_event_t;

void        cmd_parser_init(cmd_parser_t *p);
cmd_event_t cmd_parser_feed(cmd_parser_t *p, uint8_t byte);

#ifdef __cplusplus
}
#endif

#endif /* FRAME_PROTOCOL_H */
