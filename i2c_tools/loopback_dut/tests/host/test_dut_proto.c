/**
 * [v0.1]
 * test_dut_proto.c - tier T1: line protocol parser and line sealing
 * (loopback_dut/docs/PROTOCOL.md §2-3).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dut_proto.h"

static int g_checks, g_fail;
#define CHECK(c, m) do { g_checks++; if (!(c)) { g_fail++; \
    printf("  FAIL: %s (%s:%d)\n", m, __FILE__, __LINE__); } } while (0)

static dut_err_t parse(const char *s, dut_cmd_t *c)
{
    static char buf[LB_LINE_MAX + 64];
    strncpy(buf, s, sizeof buf - 1);
    buf[sizeof buf - 1] = '\0';
    return dut_parse_line(buf, c);
}

static void test_simple(void)
{
    printf("test_simple\n");
    dut_cmd_t c;
    CHECK(parse("PING", &c) == DUT_OK && c.type == DUT_CMD_PING, "PING");
    CHECK(parse("ping\r\n", &c) == DUT_OK && c.type == DUT_CMD_PING, "lower case + CRLF");
    CHECK(parse("STATUS", &c) == DUT_OK && c.type == DUT_CMD_STATUS, "STATUS");
    CHECK(parse("RESET", &c) == DUT_OK && c.type == DUT_CMD_RESET, "RESET");
    CHECK(parse("", &c) == DUT_OK && c.type == DUT_CMD_NONE, "blank line");
    CHECK(parse("PING extra", &c) == DUT_E_SYNTAX, "PING with args rejected");
    CHECK(parse("FROB", &c) == DUT_E_SYNTAX, "unknown keyword");
}

static void test_set(void)
{
    printf("test_set\n");
    dut_cmd_t c;
    CHECK(parse("SET SPEED 400000", &c) == DUT_OK && c.type == DUT_CMD_SET_SPEED &&
          c.v1 == 400000 && c.v2 == LB_RISE_NS && c.v3 == LB_FALL_NS, "SET SPEED default edges");
    CHECK(parse("SET SPEED 100000 120 15", &c) == DUT_OK && c.v2 == 120 && c.v3 == 15,
          "SET SPEED with rise/fall");
    CHECK(parse("SET SPEED 100000 120", &c) == DUT_E_SYNTAX, "SET SPEED 2 args rejected");
    CHECK(parse("SET ADDR 1 6B", &c) == DUT_OK && c.type == DUT_CMD_SET_ADDR &&
          c.resp == 1 && c.v1 == 0x6B, "SET ADDR hex");
    CHECK(parse("SET ADDR 2 0x55", &c) == DUT_OK && c.resp == 2 && c.v1 == 0x55, "SET ADDR 0x prefix");
    CHECK(parse("SET ADDR 3 55", &c) == DUT_E_ARG, "responder 3 rejected");
    CHECK(parse("SET ADDR 1 80", &c) == DUT_E_ARG, "8-bit address rejected");
    CHECK(parse("SET EN 2 0", &c) == DUT_OK && c.type == DUT_CMD_SET_EN && c.v1 == 0, "SET EN");
    CHECK(parse("SET PEC 1 2", &c) == DUT_OK && c.type == DUT_CMD_SET_PEC && c.v1 == 2, "SET PEC");
    CHECK(parse("SET STRETCH 1 1 200", &c) == DUT_OK && c.type == DUT_CMD_SET_STRETCH &&
          c.resp == 1 && c.v1 == 1 && c.v2 == 200, "SET STRETCH");
    CHECK(parse("SET STRETCH 1 1 999999", &c) == DUT_E_ARG, "stretch above limit rejected");
}

static void test_run(void)
{
    printf("test_run\n");
    dut_cmd_t c;
    CHECK(parse("RUN 7 WR 6B 2 02", &c) == DUT_OK && c.type == DUT_CMD_RUN &&
          c.seq == 7 && c.op == DUT_OP_WR && c.addr == 0x6B && c.rlen == 2 &&
          c.wlen == 1 && c.wdata[0] == 0x02 && c.rep == 1 && c.gap_us == 0, "RUN WR");
    CHECK(parse("RUN 8 W 6B 10 34 12", &c) == DUT_OK && c.op == DUT_OP_W && c.wlen == 3 &&
          c.wdata[2] == 0x12 && c.rlen == 0, "RUN W 3 bytes");
    CHECK(parse("RUN 9 R 55 4", &c) == DUT_OK && c.op == DUT_OP_R && c.rlen == 4 &&
          c.wlen == 0, "RUN R");
    CHECK(parse("RUN 10 WPR 6B 2 04", &c) == DUT_OK && c.op == DUT_OP_WPR, "RUN WPR");
    CHECK(parse("RUN 11 WR 6B 2 06 rep=200 gap=0", &c) == DUT_OK && c.rep == 200 &&
          c.gap_us == 0, "rep/gap options");
    CHECK(parse("RUN 12 WR 6B 2 06 REP=5 GAP=100", &c) == DUT_OK && c.rep == 5 &&
          c.gap_us == 100, "options case-insensitive");
    CHECK(parse("RUN 13 WR 6B 128 00", &c) == DUT_OK && c.rlen == 128, "rlen at LB_MAX_XFER");
    CHECK(parse("RUN 13 WR 6B 129 00", &c) == DUT_E_ARG, "rlen above max rejected");
    CHECK(parse("RUN 14 W 6B", &c) == DUT_E_SYNTAX, "W without data rejected");
    CHECK(parse("RUN 15 R 55 4 01", &c) == DUT_E_SYNTAX, "R with data rejected");
    CHECK(parse("RUN 16 X 55 4", &c) == DUT_E_SYNTAX, "unknown op");
    CHECK(parse("RUN 17 W 6B GG", &c) == DUT_E_ARG, "bad hex byte");
    CHECK(parse("RUN 18 W 6B 01 rep=0", &c) == DUT_E_ARG, "rep=0 rejected");
    CHECK(parse("RUN 19 W 6B 01 foo=1", &c) == DUT_E_SYNTAX, "unknown option");
}

static void test_checksum(void)
{
    printf("test_checksum\n");
    char line[64];
    dut_cmd_t c;
    /* seal a command the way the host does, then parse it                   */
    strcpy(line, "RUN 3 WR 6B 2 02");
    size_t n = dut_line_seal(line, strlen(line), sizeof line);
    CHECK(n == strlen("RUN 3 WR 6B 2 02") + 5 && line[n - 1] == '\n', "seal appends ' *CC\\n'");
    line[n] = '\0';
    CHECK(parse(line, &c) == DUT_OK && c.type == DUT_CMD_RUN && c.seq == 3,
          "sealed line parses");
    /* corrupt one character: CRC must catch it                             */
    line[4] = '4';
    CHECK(parse(line, &c) == DUT_E_CRC, "corrupted sealed line rejected");
    CHECK(dut_line_crc("123456789", 9) == 0xF4, "line CRC is CRC-8/SMBUS");
    /* PROTOCOL.md §6 vectors (computed independently in Python)          */
    const char *hello = "HELLO LBDUT proto=1 fw=0.1 kernel=64000000";
    CHECK(dut_line_crc(hello, strlen(hello)) == 0xBF, "PROTOCOL.md HELLO vector *BF");
    const char *ph = "PH 1 0 1 SR 6B R A P 2 02 A0";
    CHECK(dut_line_crc(ph, strlen(ph)) == 0xCB, "PROTOCOL.md PH vector *CB");
    CHECK(parse("PING *ZZ", &c) == DUT_E_CRC, "non-hex checksum rejected");
    char small[8] = "PING";
    CHECK(dut_line_seal(small, 4, 8) == 0, "seal refuses when cap too small");
}

int main(void)
{
    printf("=== dut_proto host tests ===\n");
    test_simple();
    test_set();
    test_run();
    test_checksum();
    printf("=== %d checks, %d failures ===\n", g_checks, g_fail);
    return g_fail ? EXIT_FAILURE : EXIT_SUCCESS;
}
