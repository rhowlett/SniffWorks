/**
 * [v0.2]
 ******************************************************************************
 * @file    frame_protocol.c
 * @brief   Binary UART framing implementation (see header / PROTOCOL.md).
 *          Pure C, no hardware access: unit-tested on the host.
 ******************************************************************************
 */
#include "frame_protocol.h"
#include "sniffer_config.h"

/* --------------------------------------------------------------------------
 * SMBus CRC-8: polynomial x^8 + x^2 + x + 1 (0x07), init 0x00.
 * Bitwise implementation - small and fast enough (frames are short).
 * Matches core/i2c_controller.py::smbus_crc8 on the Python side.
 * ------------------------------------------------------------------------ */
/* fw 1.4: table-driven CRC-8/SMBUS (poly 0x07). The bit-wise loop cost
 * ~8 x 6 cycles per byte, i.e. ~20 us for a TXN frame at 48 MHz, which
 * widened the window in which a START arriving during a frame flush is
 * missed. One lookup per byte; identical results (host test compares the
 * table against the bit-wise definition for all 256 inputs).              */
const uint8_t frame_crc8_table[256] = {
    0x00U, 0x07U, 0x0EU, 0x09U, 0x1CU, 0x1BU, 0x12U, 0x15U,
    0x38U, 0x3FU, 0x36U, 0x31U, 0x24U, 0x23U, 0x2AU, 0x2DU,
    0x70U, 0x77U, 0x7EU, 0x79U, 0x6CU, 0x6BU, 0x62U, 0x65U,
    0x48U, 0x4FU, 0x46U, 0x41U, 0x54U, 0x53U, 0x5AU, 0x5DU,
    0xE0U, 0xE7U, 0xEEU, 0xE9U, 0xFCU, 0xFBU, 0xF2U, 0xF5U,
    0xD8U, 0xDFU, 0xD6U, 0xD1U, 0xC4U, 0xC3U, 0xCAU, 0xCDU,
    0x90U, 0x97U, 0x9EU, 0x99U, 0x8CU, 0x8BU, 0x82U, 0x85U,
    0xA8U, 0xAFU, 0xA6U, 0xA1U, 0xB4U, 0xB3U, 0xBAU, 0xBDU,
    0xC7U, 0xC0U, 0xC9U, 0xCEU, 0xDBU, 0xDCU, 0xD5U, 0xD2U,
    0xFFU, 0xF8U, 0xF1U, 0xF6U, 0xE3U, 0xE4U, 0xEDU, 0xEAU,
    0xB7U, 0xB0U, 0xB9U, 0xBEU, 0xABU, 0xACU, 0xA5U, 0xA2U,
    0x8FU, 0x88U, 0x81U, 0x86U, 0x93U, 0x94U, 0x9DU, 0x9AU,
    0x27U, 0x20U, 0x29U, 0x2EU, 0x3BU, 0x3CU, 0x35U, 0x32U,
    0x1FU, 0x18U, 0x11U, 0x16U, 0x03U, 0x04U, 0x0DU, 0x0AU,
    0x57U, 0x50U, 0x59U, 0x5EU, 0x4BU, 0x4CU, 0x45U, 0x42U,
    0x6FU, 0x68U, 0x61U, 0x66U, 0x73U, 0x74U, 0x7DU, 0x7AU,
    0x89U, 0x8EU, 0x87U, 0x80U, 0x95U, 0x92U, 0x9BU, 0x9CU,
    0xB1U, 0xB6U, 0xBFU, 0xB8U, 0xADU, 0xAAU, 0xA3U, 0xA4U,
    0xF9U, 0xFEU, 0xF7U, 0xF0U, 0xE5U, 0xE2U, 0xEBU, 0xECU,
    0xC1U, 0xC6U, 0xCFU, 0xC8U, 0xDDU, 0xDAU, 0xD3U, 0xD4U,
    0x69U, 0x6EU, 0x67U, 0x60U, 0x75U, 0x72U, 0x7BU, 0x7CU,
    0x51U, 0x56U, 0x5FU, 0x58U, 0x4DU, 0x4AU, 0x43U, 0x44U,
    0x19U, 0x1EU, 0x17U, 0x10U, 0x05U, 0x02U, 0x0BU, 0x0CU,
    0x21U, 0x26U, 0x2FU, 0x28U, 0x3DU, 0x3AU, 0x33U, 0x34U,
    0x4EU, 0x49U, 0x40U, 0x47U, 0x52U, 0x55U, 0x5CU, 0x5BU,
    0x76U, 0x71U, 0x78U, 0x7FU, 0x6AU, 0x6DU, 0x64U, 0x63U,
    0x3EU, 0x39U, 0x30U, 0x37U, 0x22U, 0x25U, 0x2CU, 0x2BU,
    0x06U, 0x01U, 0x08U, 0x0FU, 0x1AU, 0x1DU, 0x14U, 0x13U,
    0xAEU, 0xA9U, 0xA0U, 0xA7U, 0xB2U, 0xB5U, 0xBCU, 0xBBU,
    0x96U, 0x91U, 0x98U, 0x9FU, 0x8AU, 0x8DU, 0x84U, 0x83U,
    0xDEU, 0xD9U, 0xD0U, 0xD7U, 0xC2U, 0xC5U, 0xCCU, 0xCBU,
    0xE6U, 0xE1U, 0xE8U, 0xEFU, 0xFAU, 0xFDU, 0xF4U, 0xF3U
};

uint8_t frame_crc8_cont(uint8_t crc, const uint8_t *data, uint32_t len)
{
    for (uint32_t i = 0U; i < len; i++)
    {
        crc = frame_crc8_table[(uint8_t)(crc ^ data[i])];
    }
    return crc;
}

uint8_t frame_crc8(const uint8_t *data, uint32_t len)
{
    return frame_crc8_cont(0x00U, data, len);
}

/* --------------------------------------------------------------------------
 * Generic frame assembly helpers
 * ------------------------------------------------------------------------ */
static uint32_t frame_seal(uint8_t *buf, uint8_t type, uint32_t payload_len)
{
    buf[0] = FRAME_SYNC_DEV2HOST;
    buf[1] = type;
    buf[2] = (uint8_t)(payload_len & 0xFFU);
    buf[3] = (uint8_t)((payload_len >> 8) & 0xFFU);
    /* CRC over type + len + payload */
    buf[4U + payload_len] = frame_crc8(&buf[1], 3U + payload_len);
    return 5U + payload_len;
}

static inline void put_u16le(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v & 0xFFU);
    p[1] = (uint8_t)(v >> 8);
}

static inline void put_u32le(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xFFU);
    p[1] = (uint8_t)((v >> 8) & 0xFFU);
    p[2] = (uint8_t)((v >> 16) & 0xFFU);
    p[3] = (uint8_t)((v >> 24) & 0xFFU);
}

/* --------------------------------------------------------------------------
 * TXN frame payload:
 *   u32 t_us | u8 addr7 | u8 flags | u8 dlen | dlen bytes | u32 scl_hz
 * scl_hz (fw >= 1.3) trails the data; hosts that size data by dlen ignore it.
 * ------------------------------------------------------------------------ */
uint32_t frame_encode_txn(uint8_t *buf, const i2c_txn_t *txn)
{
    uint8_t *p = &buf[4];
    uint32_t i;
    uint8_t flags = 0U;

    if (txn->dir_read != 0U) { flags |= TXN_FLAG_DIR_READ; }
    if (txn->nak      != 0U) { flags |= TXN_FLAG_NAK;      }
    if (txn->restart  != 0U) { flags |= TXN_FLAG_RESTART;  }
    if (txn->stop     != 0U) { flags |= TXN_FLAG_STOP;     }
    if (txn->overflow != 0U) { flags |= TXN_FLAG_OVERFLOW; }
    if (txn->timeout  != 0U) { flags |= TXN_FLAG_TIMEOUT;  }
    if (txn->framing  != 0U) { flags |= TXN_FLAG_FRAMING;  }

    put_u32le(&p[0], txn->t_us);
    p[4] = txn->addr7;
    p[5] = flags;
    p[6] = txn->len;
    for (i = 0U; i < txn->len; i++)
    {
        p[7U + i] = txn->data[i];
    }
    put_u32le(&p[7U + (uint32_t)txn->len], i2c_txn_scl_hz(txn));  /* main loop */
    return frame_seal(buf, FRAME_TYPE_TXN, 7U + (uint32_t)txn->len + 4U);
}

/* --------------------------------------------------------------------------
 * STATUS frame payload:
 *   u8 proto | u8 fw_maj | u8 fw_min | u8 mode | u8 state |
 *   u32 captured | u32 errors | u32 dropped | u32 bus_hz
 *   [fw 1.4, diag_valid] u8 diag_ver | u8 0 | u16 max_gap | u16 min_high |
 *   u16 min_low | u32 gaps_2us | u32 framing | u16 frm_max_gap |
 *   u16 frm_min_high | u32 deferred                    (PROTOCOL.md 1.2.1)
 * ------------------------------------------------------------------------ */
uint32_t frame_encode_status(uint8_t *buf, const status_info_t *st)
{
    uint8_t *p = &buf[4];

    p[0] = st->proto_ver;
    p[1] = st->fw_major;
    p[2] = st->fw_minor;
    p[3] = st->mode;
    p[4] = st->state;
    put_u32le(&p[5],  st->captured);
    put_u32le(&p[9],  st->errors);
    put_u32le(&p[13], st->dropped);
    put_u32le(&p[17], st->bus_hz);
    if (st->diag_valid == 0U)
    {
        return frame_seal(buf, FRAME_TYPE_STATUS, STATUS_PAYLOAD_LEN);
    }
    p[21] = STATUS_DIAG_VERSION;
    p[22] = 0U;
    put_u16le(&p[23], st->diag_max_gap);
    put_u16le(&p[25], st->diag_min_high);
    put_u16le(&p[27], st->diag_min_low);
    put_u32le(&p[29], st->diag_gaps_2us);
    put_u32le(&p[33], st->diag_framing);
    put_u16le(&p[37], st->diag_frm_max_gap);
    put_u16le(&p[39], st->diag_frm_min_high);
    put_u32le(&p[41], st->diag_deferred);
    return frame_seal(buf, FRAME_TYPE_STATUS, STATUS_DIAG_PAYLOAD_LEN);
}

uint32_t frame_encode_error(uint8_t *buf, uint8_t code, uint8_t detail)
{
    buf[4] = code;
    buf[5] = detail;
    return frame_seal(buf, FRAME_TYPE_ERROR, 2U);
}

/* --------------------------------------------------------------------------
 * HELLO frame payload:
 *   'N' 'C' '0' 'S' | u8 proto | u8 fw_maj | u8 fw_min | u8 mode
 * ------------------------------------------------------------------------ */
uint32_t frame_encode_hello(uint8_t *buf, uint8_t mode)
{
    uint8_t *p = &buf[4];

    p[0] = (uint8_t)HELLO_MAGIC_0;
    p[1] = (uint8_t)HELLO_MAGIC_1;
    p[2] = (uint8_t)HELLO_MAGIC_2;
    p[3] = (uint8_t)HELLO_MAGIC_3;
    p[4] = FRAME_PROTOCOL_VERSION;
    p[5] = FW_VERSION_MAJOR;
    p[6] = FW_VERSION_MINOR;
    p[7] = mode;
    return frame_seal(buf, FRAME_TYPE_HELLO, 8U);
}

/* --------------------------------------------------------------------------
 * Host -> Device command parser
 * ------------------------------------------------------------------------ */
void cmd_parser_init(cmd_parser_t *p)
{
    p->state = 0U;
    p->cmd   = 0U;
    p->arg   = 0U;
}

cmd_event_t cmd_parser_feed(cmd_parser_t *p, uint8_t byte)
{
    switch (p->state)
    {
        case 0U:
            if (byte == FRAME_SYNC_HOST2DEV)
            {
                p->state = 1U;
            }
            break;

        case 1U:
            p->cmd   = byte;
            p->state = 2U;
            break;

        case 2U:
            /* Legacy fixed commands (< CMD_VAR_MIN): this byte is the arg.
             * Variable-length commands: this byte is the payload length.   */
            p->arg = byte;
            if (p->cmd >= CMD_VAR_MIN)
            {
                p->len = byte;
                p->idx = 0U;
                if (p->len > CMD_MAX_PAYLOAD)
                {
                    p->state = 0U;              /* implausible - resync     */
                    return CMD_EVT_BAD_CRC;
                }
                p->state = (p->len > 0U) ? 4U : 3U;
            }
            else
            {
                p->state = 3U;
            }
            break;

        case 4U:                                /* var-length payload bytes */
            p->payload[p->idx++] = byte;
            if (p->idx >= p->len)
            {
                p->state = 3U;
            }
            break;

        case 3U:
        default:
        {
            p->state = 0U;
            if (p->cmd >= CMD_VAR_MIN)
            {
                /* crc over cmd, len, payload */
                uint8_t crc = frame_crc8(&p->cmd, 1U);
                crc = frame_crc8_cont(crc, &p->len, 1U);
                crc = frame_crc8_cont(crc, p->payload, p->len);
                if (crc == byte)
                {
                    return CMD_EVT_COMMAND;
                }
                return CMD_EVT_BAD_CRC;
            }
            {
                uint8_t body[2];
                body[0] = p->cmd;
                body[1] = p->arg;
                if (frame_crc8(body, 2U) == byte)
                {
                    return CMD_EVT_COMMAND;
                }
                return CMD_EVT_BAD_CRC;
            }
        }
    }
    return CMD_EVT_NONE;
}
