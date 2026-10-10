/**
 * [v0.2]
 * test_frame_protocol.c - host unit tests for the UART framing layer.
 *
 * Coverage:
 *   - SMBus CRC-8 known-answer vectors
 *   - TXN frame round-trip (encode -> manual decode), incl. trailing scl_hz
 *   - STATUS / ERROR / HELLO frame layout
 *   - command parser: happy path, bad CRC, garbage resync
 *   - fw 1.4: CRC lookup table == bit-wise definition; STATUS diag block
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "frame_protocol.h"
#include "sniffer_config.h"

static int g_failures = 0;
static int g_checks   = 0;

#define CHECK(cond, msg) do {                                        \
    g_checks++;                                                      \
    if (!(cond)) {                                                   \
        g_failures++;                                                \
        printf("  FAIL: %s  (%s:%d)\n", msg, __FILE__, __LINE__);    \
    }                                                                \
} while (0)

static uint32_t get_u32le(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* ------------------------------------------------------------------------ */
static void test_crc8_vectors(void)
{
    printf("test_crc8_vectors\n");

    /* CRC-8/SMBUS check value: "123456789" -> 0xF4                          */
    const uint8_t check[] = "123456789";
    CHECK(frame_crc8(check, 9) == 0xF4, "standard check string -> 0xF4");

    CHECK(frame_crc8(NULL, 0) == 0x00, "empty -> 0x00");

    const uint8_t one_zero[] = { 0x00 };
    CHECK(frame_crc8(one_zero, 1) == 0x00, "single 0x00 -> 0x00");

    /* SMBus PEC example: addr(0x5A<<1|0)=0xB4, cmd 0x06, data 0x00 0x01     */
    const uint8_t pec_msg[] = { 0xB4, 0x06, 0x00, 0x01 };
    const uint8_t expect = frame_crc8(pec_msg, 4);
    /* self-consistency: appending the CRC must yield residual 0             */
    uint8_t with_crc[5];
    memcpy(with_crc, pec_msg, 4);
    with_crc[4] = expect;
    CHECK(frame_crc8(with_crc, 5) == 0x00, "message+CRC residual is zero");
}

/* ------------------------------------------------------------------------ */
static uint8_t crc8_bitwise(uint8_t crc, uint8_t b)
{
    crc ^= b;
    for (int i = 0; i < 8; i++)
    {
        crc = (uint8_t)((crc & 0x80U) ? (((unsigned)crc << 1) ^ 0x07U) : ((unsigned)crc << 1));
    }
    return crc;
}

static void test_crc_table(void)
{
    printf("test_crc_table\n");
    int ok = 1;
    for (unsigned i = 0; i < 256U; i++)
    {
        if (frame_crc8_table[i] != crc8_bitwise(0U, (uint8_t)i)) { ok = 0; }
    }
    CHECK(ok, "table == bit-wise CRC-8/SMBUS for all 256 inputs");
    uint8_t buf[300];
    uint8_t ref = 0U;
    for (unsigned i = 0; i < sizeof buf; i++)
    {
        buf[i] = (uint8_t)(i * 37U + 11U);
        ref = crc8_bitwise(ref, buf[i]);
    }
    CHECK(frame_crc8(buf, sizeof buf) == ref, "300-byte message: table == bit-wise");
    CHECK(frame_crc8_cont(frame_crc8(buf, 100U), &buf[100], 200U) == ref, "continued CRC == one-shot");
}

static void test_status_diag(void)
{
    printf("test_status_diag\n");
    uint8_t buf[FRAME_MAX_ENCODED];
    status_info_t st;
    memset(&st, 0, sizeof st);
    st.proto_ver = FRAME_PROTOCOL_VERSION;
    st.diag_valid = 1U;
    st.diag_max_gap = 0x1234U;   st.diag_min_high = 0x00F0U; st.diag_min_low = 0x0100U;
    st.diag_gaps_2us = 7U;       st.diag_framing = 3U;
    st.diag_frm_max_gap = 0x0BB8U; st.diag_frm_min_high = 0x0030U;
    st.diag_deferred = 0xA5A5A5A5U;
    const uint32_t n = frame_encode_status(buf, &st);
    CHECK(n == 5U + STATUS_DIAG_PAYLOAD_LEN, "STATUS with diag: 45-byte payload");
    CHECK((buf[2] | (buf[3] << 8)) == 45, "payload length field 45");
    const uint8_t *p = &buf[4];
    CHECK(p[21] == STATUS_DIAG_VERSION && p[22] == 0U, "diag version 1 at offset 21");
    CHECK((p[23] | (p[24] << 8)) == 0x1234 && (p[25] | (p[26] << 8)) == 0x00F0 &&
          (p[27] | (p[28] << 8)) == 0x0100, "max_gap / min_high / min_low LE");
    CHECK(get_u32le(&p[29]) == 7U && get_u32le(&p[33]) == 3U, "gaps_2us / framing LE");
    CHECK((p[37] | (p[38] << 8)) == 0x0BB8 && (p[39] | (p[40] << 8)) == 0x0030,
          "frm_max_gap / frm_min_high LE");
    CHECK(get_u32le(&p[41]) == 0xA5A5A5A5U, "deferred LE at offset 41");
    CHECK(frame_crc8(&buf[1], n - 2U) == buf[n - 1U], "CRC valid");
    st.diag_valid = 0U;
    CHECK(frame_encode_status(buf, &st) == 5U + STATUS_PAYLOAD_LEN, "diag_valid 0: classic 21-byte STATUS");
}

/* ------------------------------------------------------------------------ */
static void test_txn_roundtrip(void)
{
    printf("test_txn_roundtrip\n");
    uint8_t buf[FRAME_MAX_ENCODED];
    i2c_txn_t t;

    memset(&t, 0, sizeof t);
    t.t_us     = 0xDEADBEEFU;
    t.addr7    = 0x08;
    t.dir_read = 1;
    t.nak      = 1;
    t.restart  = 1;
    t.stop     = 1;
    t.len      = 3;
    t.data[0]  = 0xAA; t.data[1] = 0x55; t.data[2] = 0x0F;
    t.scl_sum_us = 25U; t.scl_cnt = 10U;      /* 2.5 us mean -> 400 kHz  */

    const uint32_t n = frame_encode_txn(buf, &t);

    CHECK(n == 5U + 7U + 3U + 4U, "encoded length (fw 1.3: + u32 scl_hz)");
    CHECK(buf[0] == FRAME_SYNC_DEV2HOST, "sync byte");
    CHECK(buf[1] == FRAME_TYPE_TXN, "type TXN");
    CHECK((buf[2] | (buf[3] << 8)) == 14, "payload length field");
    CHECK(get_u32le(&buf[4]) == 0xDEADBEEFU, "timestamp LE");
    CHECK(buf[8] == 0x08, "addr7");
    CHECK(buf[9] == (TXN_FLAG_DIR_READ | TXN_FLAG_NAK |
                     TXN_FLAG_RESTART | TXN_FLAG_STOP), "flags");
    CHECK(buf[10] == 3, "dlen");
    CHECK(buf[11] == 0xAA && buf[12] == 0x55 && buf[13] == 0x0F, "data");
    CHECK(get_u32le(&buf[14]) == 400000U, "scl_hz LE right after data");
    CHECK(frame_crc8(&buf[1], n - 2U) == buf[n - 1U], "CRC valid");
}

/* ------------------------------------------------------------------------ */
static void test_txn_scl_hz_placement(void)
{
    printf("test_txn_scl_hz_placement\n");
    uint8_t buf[FRAME_MAX_ENCODED];
    i2c_txn_t t;

    /* zero-length phase: scl_hz sits at payload offset 7                   */
    memset(&t, 0, sizeof t);
    t.addr7 = 0x08; t.nak = 1; t.stop = 1;
    t.scl_sum_us = 81U; t.scl_cnt = 8U;        /* 10.125 us -> 98765 Hz   */
    uint32_t n = frame_encode_txn(buf, &t);
    CHECK(n == 5U + 7U + 4U, "0-byte phase: 7 + 4 payload bytes");
    CHECK(buf[10] == 0U, "dlen 0");
    CHECK(get_u32le(&buf[11]) == 98765U, "scl_hz (rounded) at offset 7 when dlen 0");

    /* not measured -> 0 on the wire                                        */
    t.scl_sum_us = 0U; t.scl_cnt = 0U;
    frame_encode_txn(buf, &t);
    CHECK(get_u32le(&buf[11]) == 0U, "unmeasured scl_hz encodes as 0");
    t.scl_sum_us = 30U; t.scl_cnt = I2C_DEC_SCL_MIN_PERIODS - 1U;
    frame_encode_txn(buf, &t);
    CHECK(get_u32le(&buf[11]) == 0U, "too few periods encodes as 0");

    /* full payload still fits FRAME_MAX_ENCODED                            */
    memset(&t, 0, sizeof t);
    t.len = TXN_MAX_DATA; t.scl_sum_us = 4000U; t.scl_cnt = 4000U;  /* 1 MHz */
    n = frame_encode_txn(buf, &t);
    CHECK(n == FRAME_MAX_ENCODED, "max TXN frame == FRAME_MAX_ENCODED");
    CHECK(get_u32le(&buf[11U + TXN_MAX_DATA]) == 1000000U,
          "scl_hz after a full 64-byte payload");
    CHECK(frame_crc8(&buf[1], n - 2U) == buf[n - 1U], "max frame CRC valid");
}

/* ------------------------------------------------------------------------ */
static void test_status_layout(void)
{
    printf("test_status_layout\n");
    uint8_t buf[FRAME_MAX_ENCODED];
    status_info_t st = {
        .proto_ver = FRAME_PROTOCOL_VERSION,
        .fw_major  = 1, .fw_minor = 0,
        .mode      = SNIFF_MODE_BITBANG,
        .state     = CAPTURE_STATE_RUNNING,
        .captured  = 123456,
        .errors    = 7,
        .dropped   = 2,
        .bus_hz    = 100000,
    };

    const uint32_t n = frame_encode_status(buf, &st);
    CHECK(n == 5U + 21U, "status frame length");
    CHECK(buf[1] == FRAME_TYPE_STATUS, "type");
    CHECK(buf[4] == FRAME_PROTOCOL_VERSION, "proto ver");
    CHECK(buf[7] == SNIFF_MODE_BITBANG, "mode");
    CHECK(buf[8] == CAPTURE_STATE_RUNNING, "state");
    CHECK(get_u32le(&buf[9])  == 123456, "captured");
    CHECK(get_u32le(&buf[13]) == 7, "errors");
    CHECK(get_u32le(&buf[17]) == 2, "dropped");
    CHECK(get_u32le(&buf[21]) == 100000, "bus_hz");
    CHECK(frame_crc8(&buf[1], n - 2U) == buf[n - 1U], "CRC valid");
}

/* ------------------------------------------------------------------------ */
static void test_hello_and_error(void)
{
    printf("test_hello_and_error\n");
    uint8_t buf[FRAME_MAX_ENCODED];

    uint32_t n = frame_encode_hello(buf, SNIFF_MODE_BITBANG);
    CHECK(buf[1] == FRAME_TYPE_HELLO, "hello type");
    CHECK(buf[4] == 'N' && buf[5] == 'C' && buf[6] == '0' && buf[7] == 'S',
          "hello magic NC0S");
    CHECK(buf[8] == FRAME_PROTOCOL_VERSION, "hello proto");
    CHECK(frame_crc8(&buf[1], n - 2U) == buf[n - 1U], "hello CRC");

    n = frame_encode_error(buf, ERR_CODE_RING_OVERFLOW, 0x42);
    CHECK(buf[1] == FRAME_TYPE_ERROR, "error type");
    CHECK(buf[4] == ERR_CODE_RING_OVERFLOW && buf[5] == 0x42, "error payload");
    CHECK(frame_crc8(&buf[1], n - 2U) == buf[n - 1U], "error CRC");
}

/* ------------------------------------------------------------------------ */
static void test_cmd_parser(void)
{
    printf("test_cmd_parser\n");
    cmd_parser_t p;
    cmd_parser_init(&p);

    /* happy path: START command                                             */
    uint8_t body[2] = { CMD_START, 0x00 };
    const uint8_t crc = frame_crc8(body, 2);

    CHECK(cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV) == CMD_EVT_NONE, "sync");
    CHECK(cmd_parser_feed(&p, CMD_START) == CMD_EVT_NONE, "cmd byte");
    CHECK(cmd_parser_feed(&p, 0x00) == CMD_EVT_NONE, "arg byte");
    CHECK(cmd_parser_feed(&p, crc) == CMD_EVT_COMMAND, "complete command");
    CHECK(p.cmd == CMD_START && p.arg == 0x00, "fields");

    /* bad CRC                                                               */
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, CMD_STOP);
    cmd_parser_feed(&p, 0x00);
    CHECK(cmd_parser_feed(&p, (uint8_t)(crc ^ 0xFF)) == CMD_EVT_BAD_CRC,
          "bad CRC detected");

    /* garbage resync: junk, then a valid PING                               */
    for (uint8_t junk = 1; junk < 20; junk++)
    {
        if (junk != FRAME_SYNC_HOST2DEV)
        {
            CHECK(cmd_parser_feed(&p, junk) == CMD_EVT_NONE, "junk ignored");
        }
    }
    body[0] = CMD_PING; body[1] = 0;
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, CMD_PING);
    cmd_parser_feed(&p, 0x00);
    CHECK(cmd_parser_feed(&p, frame_crc8(body, 2)) == CMD_EVT_COMMAND,
          "resync to valid command");
    CHECK(p.cmd == CMD_PING, "ping parsed");
}


/* ------------------------------------------------------------------------ */
static void test_cmd_parser_varlen(void)
{
    cmd_parser_t p;
    cmd_parser_init(&p);

    /* CMD_I2C_WRITE: addr 0x08, data {0x3E} -> A5 10 02 08 3E crc          */
    uint8_t body[80];
    body[0] = CMD_I2C_WRITE;
    body[1] = 2;                /* len */
    body[2] = 0x08;
    body[3] = 0x3E;
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, body[0]);
    cmd_parser_feed(&p, body[1]);
    cmd_parser_feed(&p, body[2]);
    cmd_parser_feed(&p, body[3]);
    CHECK(cmd_parser_feed(&p, frame_crc8(body, 4)) == CMD_EVT_COMMAND,
          "var-length I2C_WRITE parsed");
    CHECK(p.cmd == CMD_I2C_WRITE && p.len == 2 &&
          p.payload[0] == 0x08 && p.payload[1] == 0x3E,
          "var-length payload captured");

    /* zero-length payload (SET_BUS_SPEED malformed as len=0 still frames)  */
    body[0] = CMD_SET_BUS_SPEED; body[1] = 0;
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, body[0]);
    cmd_parser_feed(&p, body[1]);
    CHECK(cmd_parser_feed(&p, frame_crc8(body, 2)) == CMD_EVT_COMMAND,
          "zero-payload var command frames");
    CHECK(p.len == 0, "zero payload length");

    /* corrupt CRC on a var command -> BAD_CRC, then a legacy PING parses   */
    body[0] = CMD_I2C_READ; body[1] = 2; body[2] = 0x08; body[3] = 4;
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, body[0]);
    cmd_parser_feed(&p, body[1]);
    cmd_parser_feed(&p, body[2]);
    cmd_parser_feed(&p, body[3]);
    CHECK(cmd_parser_feed(&p, (uint8_t)(frame_crc8(body, 4) ^ 0xFF))
              == CMD_EVT_BAD_CRC, "var-length bad CRC detected");
    body[0] = CMD_PING; body[1] = 0;
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, CMD_PING);
    cmd_parser_feed(&p, 0x00);
    CHECK(cmd_parser_feed(&p, frame_crc8(body, 2)) == CMD_EVT_COMMAND,
          "legacy command still parses after var-length");

    /* implausible length rejected immediately                              */
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, CMD_I2C_WRITE);
    CHECK(cmd_parser_feed(&p, 0xFF) == CMD_EVT_BAD_CRC,
          "oversize var length rejected");

    /* max-size payload accepted                                            */
    body[0] = CMD_I2C_WRITE; body[1] = CMD_MAX_PAYLOAD;
    for (unsigned i = 0; i < CMD_MAX_PAYLOAD; i++) body[2 + i] = (uint8_t)i;
    cmd_parser_feed(&p, FRAME_SYNC_HOST2DEV);
    cmd_parser_feed(&p, body[0]);
    cmd_parser_feed(&p, body[1]);
    for (unsigned i = 0; i < CMD_MAX_PAYLOAD; i++) cmd_parser_feed(&p, body[2 + i]);
    CHECK(cmd_parser_feed(&p, frame_crc8(body, 2 + CMD_MAX_PAYLOAD))
              == CMD_EVT_COMMAND, "max payload accepted");
    CHECK(p.payload[CMD_MAX_PAYLOAD - 1] == CMD_MAX_PAYLOAD - 1,
          "max payload content intact");
}

/* ------------------------------------------------------------------------ */
static void test_txn_timeout_flag(void)
{
    i2c_txn_t txn = {0};
    uint8_t buf[FRAME_MAX_ENCODED];
    txn.addr7 = 0x08; txn.timeout = 1; txn.nak = 1; txn.stop = 1;
    frame_encode_txn(buf, &txn);
    CHECK((buf[9] & TXN_FLAG_TIMEOUT) != 0, "TIMEOUT flag encoded (bit 5)");
    CHECK((buf[9] & TXN_FLAG_NAK) != 0, "NAK coexists with TIMEOUT");
}

/* ------------------------------------------------------------------------ */
static void test_txn_framing_flag(void)
{
    i2c_txn_t txn = {0};
    uint8_t buf[FRAME_MAX_ENCODED];
    txn.addr7 = 0x21; txn.restart = 1; txn.stop = 1; txn.framing = 1;
    frame_encode_txn(buf, &txn);
    CHECK(buf[9] == (TXN_FLAG_RESTART | TXN_FLAG_STOP | TXN_FLAG_FRAMING),
          "FRAMING flag encoded (bit 6)");
    txn.framing = 0;
    frame_encode_txn(buf, &txn);
    CHECK((buf[9] & TXN_FLAG_FRAMING) == 0, "FRAMING clear by default");
}

/* ------------------------------------------------------------------------ */
int main(void)
{
    printf("=== frame_protocol host tests ===\n");
    test_crc8_vectors();
    test_crc_table();
    test_txn_roundtrip();
    test_status_diag();
    test_txn_scl_hz_placement();
    test_status_layout();
    test_hello_and_error();
    test_cmd_parser();
    test_cmd_parser_varlen();
    test_txn_timeout_flag();
    test_txn_framing_flag();

    printf("=== %d checks, %d failures ===\n", g_checks, g_failures);
    return (g_failures == 0) ? EXIT_SUCCESS : EXIT_FAILURE;
}
