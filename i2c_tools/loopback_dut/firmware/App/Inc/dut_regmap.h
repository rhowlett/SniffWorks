/**
 * [v0.1]
 * @file    dut_regmap.h
 * @brief   Synthetic responder register map + SMBus CRC-8. Pure C: no HAL,
 *          compiled unchanged by loopback_dut/tests/host.
 *
 * The map is documented in loopback_dut/docs/PROTOCOL.md §4. Summary:
 *
 *   Pointer = first byte of every write phase. Reads start at the pointer.
 *
 *   Word region (pointer != 0x3E..0x61):
 *     read byte k = byte (k & 1) of word(ptr + k/2), little-endian,
 *     word(x) = (base + x) & 0xFFFF         (base 0xA000 R1, 0xB000 R2)
 *     e.g. R1, ptr 0x02, 4 bytes -> 02 A0 03 A0
 *
 *   Subcommand block (pointer 0x3E..0x61, byte-addressed, TI BQ769x shape,
 *   matches DecodeSchema._unwrap_subcommand_block):
 *     0x3E/0x3F  echo of the last subcommand written to 0x3E (LE)
 *     0x40..0x5F buf[i] = (0x40 + i) XOR (subcmd & 0xFF)
 *     0x60       ~(lo + hi + sum(buf)) & 0xFF
 *     0x61       36 (= 32 + 4)
 *     past 0x61  0xFF
 *
 *   Writes: byte 0 = pointer; if pointer == 0x3E, bytes 1..2 set the
 *   subcommand (LE). Other written data is acknowledged and counted only.
 */
#ifndef DUT_REGMAP_H
#define DUT_REGMAP_H

#include <stdint.h>

#define DUT_BLOCK_START     0x3EU
#define DUT_BLOCK_END       0x61U
#define DUT_BLOCK_LEN       36U       /* 0x3E..0x61 inclusive              */
#define DUT_BLOCK_DATA_LEN  32U

typedef struct
{
    uint16_t base;      /* word base (0xA000 / 0xB000)                     */
    uint8_t  ptr;       /* register pointer (persists across STOP)         */
    uint16_t subcmd;    /* last subcommand written to 0x3E                 */
    uint8_t  sub_lo;    /* assembling a subcommand write                   */
} dut_regmap_t;

void    dut_regmap_init(dut_regmap_t *m, uint16_t base);

/** Byte `index` of a write phase (0 = pointer). */
void    dut_regmap_write(dut_regmap_t *m, uint32_t index, uint8_t byte);

/** Byte `k` (0-based) of a read phase that starts at the current pointer. */
uint8_t dut_regmap_read(const dut_regmap_t *m, uint32_t k);

/** SMBus CRC-8: poly 0x07, init 0x00, no reflection, no final XOR. */
static inline uint8_t dut_crc8_update(uint8_t crc, uint8_t byte)
{
    crc ^= byte;
    for (int i = 0; i < 8; i++)
    {
        crc = (uint8_t)((crc & 0x80U) ? (((uint32_t)crc << 1) ^ 0x07U)
                                      : ((uint32_t)crc << 1));
    }
    return crc;
}

uint8_t dut_crc8(const uint8_t *p, uint32_t n);

#endif /* DUT_REGMAP_H */
