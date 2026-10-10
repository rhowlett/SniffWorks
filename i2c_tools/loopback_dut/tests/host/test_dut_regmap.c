/**
 * [v0.1]
 * test_dut_regmap.c - tier T1: the documented register-map function
 * (PROTOCOL.md §4) byte for byte. These literal vectors are the contract the
 * Python dry-run model must also reproduce.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dut_regmap.h"

static int g_checks, g_fail;
#define CHECK(c, m) do { g_checks++; if (!(c)) { g_fail++; \
    printf("  FAIL: %s (%s:%d)\n", m, __FILE__, __LINE__); } } while (0)

static void read_n(const dut_regmap_t *m, uint8_t *out, uint32_t n)
{
    for (uint32_t k = 0; k < n; k++) { out[k] = dut_regmap_read(m, k); }
}

static void test_word_region(void)
{
    printf("test_word_region\n");
    dut_regmap_t r1, r2;
    uint8_t b[8];
    dut_regmap_init(&r1, 0xA000);
    dut_regmap_init(&r2, 0xB000);

    dut_regmap_write(&r1, 0, 0x02);                 /* pointer 0x02         */
    read_n(&r1, b, 4);
    const uint8_t want1[] = { 0x02, 0xA0, 0x03, 0xA0 };
    CHECK(memcmp(b, want1, 4) == 0, "R1 ptr 0x02 x4 = 02 A0 03 A0 (LE words)");

    dut_regmap_write(&r2, 0, 0x02);
    read_n(&r2, b, 2);
    CHECK(b[0] == 0x02 && b[1] == 0xB0, "R2 differs from R1 (base 0xB000)");

    dut_regmap_write(&r1, 0, 0x00);
    read_n(&r1, b, 2);
    CHECK(b[0] == 0x00 && b[1] == 0xA0, "R1 ptr 0x00 = 00 A0");

    dut_regmap_write(&r1, 0, 0xFF);
    read_n(&r1, b, 4);
    CHECK(b[0] == 0xFF && b[1] == 0xA0 && b[2] == 0x00 && b[3] == 0xA1,
          "ptr 0xFF: word 0xA0FF then 0xA100 (no pointer wrap)");

    /* data bytes after the pointer do not change reads                    */
    dut_regmap_write(&r1, 0, 0x10);
    dut_regmap_write(&r1, 1, 0x34);
    dut_regmap_write(&r1, 2, 0x12);
    read_n(&r1, b, 2);
    CHECK(b[0] == 0x10 && b[1] == 0xA0, "written data ignored: reads stay pure");

    /* 80-byte read (LB-11): byte 79 = hi(word(ptr + 39))                   */
    dut_regmap_write(&r1, 0, 0x00);
    CHECK(dut_regmap_read(&r1, 78) == 0x27 && dut_regmap_read(&r1, 79) == 0xA0,
          "80-byte read ends 27 A0");
}

static void test_block_region(void)
{
    printf("test_block_region\n");
    dut_regmap_t m;
    uint8_t b[40];
    dut_regmap_init(&m, 0xA000);

    /* subcommand 0x0001 written to 0x3E                                    */
    dut_regmap_write(&m, 0, 0x3E);
    dut_regmap_write(&m, 1, 0x01);
    dut_regmap_write(&m, 2, 0x00);
    CHECK(m.subcmd == 0x0001, "subcommand latched");

    dut_regmap_write(&m, 0, 0x3E);                  /* pointer only         */
    read_n(&m, b, 38);
    CHECK(b[0] == 0x01 && b[1] == 0x00, "echo 01 00");
    CHECK(b[2] == (0x40 ^ 0x01) && b[3] == (0x41 ^ 0x01) && b[33] == (0x5F ^ 0x01),
          "buf[i] = (0x40+i) ^ lo");
    uint32_t sum = b[0] + b[1];
    for (int i = 2; i < 34; i++) { sum += b[i]; }
    CHECK(b[34] == (uint8_t)~sum, "checksum = ~(lo+hi+sum(buf))");
    CHECK(b[35] == 36, "length = 36");
    CHECK(b[36] == 0xFF && b[37] == 0xFF, "past 0x61 reads 0xFF");

    /* pinned literal values for subcmd 0x0001 (host model must match)      */
    CHECK(b[34] == 0x0E, "checksum literal for subcmd 0x0001 is 0x0E");

    /* byte-addressed inside the block                                      */
    dut_regmap_write(&m, 0, 0x60);
    CHECK(dut_regmap_read(&m, 0) == b[34] && dut_regmap_read(&m, 1) == 36,
          "ptr 0x60 reads checksum, length");

    /* a different subcommand changes echo + checksum                       */
    dut_regmap_write(&m, 0, 0x3E);
    dut_regmap_write(&m, 1, 0x72);
    dut_regmap_write(&m, 2, 0x00);
    dut_regmap_write(&m, 0, 0x3E);
    CHECK(dut_regmap_read(&m, 0) == 0x72 && dut_regmap_read(&m, 2) == (0x40 ^ 0x72),
          "subcmd 0x0072 echo + buffer");
}

static void test_crc8(void)
{
    printf("test_crc8\n");
    const uint8_t v[] = "123456789";
    CHECK(dut_crc8(v, 9) == 0xF4, "CRC-8/SMBUS check value 0xF4");
    CHECK(dut_crc8((const uint8_t *)"", 0) == 0x00, "empty = 0");
    /* SMBus write-byte PEC: addr 0x6B W (0xD6), cmd 0x0A, data 0x5A        */
    const uint8_t wb[] = { 0xD6, 0x0A, 0x5A };
    const uint8_t pec = dut_crc8(wb, 3);
    const uint8_t with[] = { 0xD6, 0x0A, 0x5A, pec };
    CHECK(dut_crc8(with, 4) == 0x00, "message + PEC residual is 0");
}

int main(void)
{
    printf("=== dut_regmap host tests ===\n");
    test_word_region();
    test_block_region();
    test_crc8();
    printf("=== %d checks, %d failures ===\n", g_checks, g_fail);
    return g_fail ? EXIT_FAILURE : EXIT_SUCCESS;
}
